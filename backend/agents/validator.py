"""Validator Agent — compares extracted fields against customer rules.

Uses Claude as a true Tool-Calling Agent. For each field, Claude determines the match status. 
It has access to deterministic tools (numeric tolerance, fuzzy matching) to evaluate complex rules.
"""

import json
import logging
import re
import time
from typing import Optional
import os

from litellm import completion
from thefuzz import fuzz

from backend.config.settings import settings
from backend.prompts.loader import load_prompt
from backend.models.rules import CustomerRuleSet, FieldRule
from backend.models.schemas import (
    ExtractionResult,
    ExtractedField,
    FieldValidation,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# Ensure API keys are set in environment for litellm
if settings.anthropic_api_key:
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
if settings.openai_api_key:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key

VALIDATION_SYSTEM_PROMPT = load_prompt("validation_system.md")

# --- Deterministic Functions (Exposed as Tools) ---

UNIT_CONVERSIONS = {
    ("KG", "MT"): 0.001,
    ("MT", "KG"): 1000.0,
    ("KG", "LBS"): 2.20462,
    ("LBS", "KG"): 0.453592,
    ("MT", "LBS"): 2204.62,
    ("LBS", "MT"): 0.000453592,
}

def _extract_numeric(text: str) -> tuple[Optional[float], Optional[str]]:
    """Parse numeric value and unit from strings like '4,250 KG', '4.250 MT'."""
    if not text:
        return None, None
    text = text.strip()
    unit_match = re.search(r"(KG|MT|LBS|PCS|CTNS|CBM|SETS|NOS)", text.upper())
    unit = unit_match.group(1) if unit_match else None
    num_str = re.sub(r"[^\d.,\-]", "", text)
    if not num_str:
        return None, unit
    if "," in num_str and "." in num_str:
        num_str = num_str.replace(",", "")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts[-1]) == 3:
            num_str = num_str.replace(",", "")
        else:
            num_str = num_str.replace(",", ".")
    try:
        return float(num_str), unit
    except ValueError:
        return None, unit

def numeric_tolerance_match(found: str, expected: str, tolerance_pct: float = 2.0) -> dict:
    """Tool: Numeric comparison with unit conversion and tolerance."""
    found_num, found_unit = _extract_numeric(found)
    expected_num, expected_unit = _extract_numeric(expected)

    if found_num is None or expected_num is None:
        return {"result": "uncertain", "confidence": 0.5, "reasoning": "Could not parse numbers"}

    if found_unit and expected_unit and found_unit != expected_unit:
        conversion = UNIT_CONVERSIONS.get((found_unit, expected_unit))
        if conversion:
            found_num = found_num * conversion
        else:
            return {"result": "uncertain", "confidence": 0.5, "reasoning": f"Cannot convert {found_unit} to {expected_unit}"}

    if expected_num == 0:
        return {"result": "match" if found_num == 0 else "mismatch", "confidence": 1.0, "reasoning": "Zero check"}

    pct_diff = abs(found_num - expected_num) / abs(expected_num) * 100

    if pct_diff <= tolerance_pct:
        return {"result": "match", "confidence": max(0.0, 1.0 - pct_diff / 100.0), "reasoning": f"Difference {pct_diff:.2f}% <= {tolerance_pct}%"}
    elif pct_diff <= tolerance_pct * 2:
        return {"result": "uncertain", "confidence": 0.5, "reasoning": f"Difference {pct_diff:.2f}% is marginal"}
    else:
        return {"result": "mismatch", "confidence": max(0.0, 1.0 - pct_diff / 100.0), "reasoning": f"Difference {pct_diff:.2f}% > {tolerance_pct}%"}


def fuzzy_match(found: str, expected: str, threshold: float = 0.85) -> dict:
    """Tool: Jaro-Winkler / token sort fuzzy matching."""
    token_score = fuzz.token_sort_ratio(found.lower(), expected.lower()) / 100.0
    partial_score = fuzz.partial_ratio(found.lower(), expected.lower()) / 100.0
    score = max(token_score, partial_score)

    if score >= threshold:
        return {"result": "match", "confidence": score, "reasoning": f"Fuzzy score {score:.2f} >= {threshold}"}
    elif score >= threshold - 0.10:
        return {"result": "uncertain", "confidence": score, "reasoning": f"Fuzzy score {score:.2f} is marginal"}
    else:
        return {"result": "mismatch", "confidence": score, "reasoning": f"Fuzzy score {score:.2f} < {threshold}"}


# --- Standard OpenAI Tools ---

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "evaluate_numeric_tolerance",
            "description": "Evaluate if two numeric strings (with units) match within a given percentage tolerance. Use this for math and unit conversions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "found": {"type": "string"},
                    "expected": {"type": "string"},
                    "tolerance_pct": {"type": "number"}
                },
                "required": ["found", "expected", "tolerance_pct"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_fuzzy_match",
            "description": "Calculate a fuzzy string match score. Use this when strings might have slight typos or extra words.",
            "parameters": {
                "type": "object",
                "properties": {
                    "found": {"type": "string"},
                    "expected": {"type": "string"},
                    "threshold": {"type": "number", "default": 0.85}
                },
                "required": ["found", "expected"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_validation_result",
            "description": "Submit the final field-by-field validation results after evaluating all rules.",
            "parameters": {
                "type": "object",
                "properties": {
                    "validations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "rule_name": {"type": "string"},
                                "result": {"type": "string", "enum": ["match", "mismatch", "uncertain"]},
                                "match_confidence": {"type": "number"},
                                "reasoning": {"type": "string"}
                            },
                            "required": ["rule_name", "result", "match_confidence", "reasoning"]
                        }
                    }
                },
                "required": ["validations"]
            }
        }
    }
]

def get_expected_for_ui(rule: FieldRule) -> str:
    if rule.expected:
        return rule.expected
    if rule.match_type == "format":
        return f"Format: {rule.pattern}"
    if rule.match_type == "regex":
        return f"Regex: {rule.pattern}"
    if rule.match_type == "cross_document_consistent":
        return "Match across docs"
    if rule.match_type == "present_on_all":
        return "Present on all docs"
    return "N/A"

# --- Main Validator Agent ---

def validate_document(
    extraction: ExtractionResult,
    rules: CustomerRuleSet,
) -> ValidationResult:
    start_time = time.time()
    
    extracted_data = extraction.extracted_data
    doc_type = extraction.document_type
    field_validations = []
    
    # 1. Pre-process deterministic logic (missing fields, low confidence)
    # This saves LLM tokens and ensures strict bounds on confidence.
    items_to_validate = []
    metadata_map = {}
    
    for rule_name, rule in rules.rules.items():
        if rule.match_type in ("cross_document_consistent", "present_on_all"):
            continue
            
        field_name = rule.field if rule.field else rule_name
        
        extracted_field = None
        if hasattr(extracted_data, field_name):
            extracted_field = getattr(extracted_data, field_name)
        elif hasattr(extracted_data, rule_name):
            extracted_field = getattr(extracted_data, rule_name)
        else:
            name_mappings = {
                "incoterm": "incoterms", "incoterms": "incoterms",
                "hs_code_format": "hs_code", "weight_cross_doc": "gross_weight",
                "invoice_on_all_docs": "invoice_number",
            }
            mapped = name_mappings.get(rule_name)
            if mapped and hasattr(extracted_data, mapped):
                extracted_field = getattr(extracted_data, mapped)
                field_name = mapped
                
        expected_ui = get_expected_for_ui(rule)
        
        # Missing Field Logic
        if extracted_field is None or not isinstance(extracted_field, ExtractedField):
            expected_fields = {
                "bill_of_lading": {"consignee_name", "gross_weight", "port_of_loading", "port_of_discharge", "incoterms", "invoice_number"},
                "commercial_invoice": {"consignee_name", "invoice_number", "hs_code", "incoterms"},
                "packing_list": {"consignee_name", "invoice_number", "gross_weight", "net_weight"},
                "certificate_of_origin": {"consignee_name", "country_of_origin", "invoice_number", "hs_code"},
            }
            is_expected = (doc_type in expected_fields and field_name in expected_fields[doc_type])
            
            if rule.required and is_expected:
                field_validations.append(FieldValidation(
                    field_name=field_name, document_type=doc_type, found_value=None,
                    expected_value=expected_ui, result="mismatch", match_confidence=1.0,
                    extraction_confidence=0.0, severity=rule.severity,
                    reasoning=f"Required field '{rule_name}' not found."
                ))
            continue
            
        found_value = extracted_field.value
        extraction_conf = extracted_field.confidence
        
        # Empty Field Logic
        if not found_value or str(found_value).strip() == "":
            if rule.required:
                field_validations.append(FieldValidation(
                    field_name=field_name, document_type=doc_type, found_value=None,
                    expected_value=expected_ui, result="mismatch", match_confidence=1.0,
                    extraction_confidence=extraction_conf, severity=rule.severity,
                    reasoning=f"Required field '{field_name}' is empty."
                ))
            continue
            
        # Low Confidence Logic
        if extraction_conf < settings.confidence_threshold:
            field_validations.append(FieldValidation(
                field_name=field_name, document_type=doc_type, found_value=found_value,
                expected_value=expected_ui, result="uncertain", match_confidence=0.0,
                extraction_confidence=extraction_conf, severity=rule.severity,
                reasoning=f"Extraction confidence too low ({extraction_conf:.2f})."
            ))
            continue
            
        # Add to LLM evaluation list
        items_to_validate.append({
            "rule_name": rule_name,
            "found_value": found_value,
            "expected_value": rule.expected,
            "match_type": rule.match_type,
            "rule_details": {
                "tolerance_pct": rule.tolerance_pct,
                "pattern": rule.pattern,
                "digits": rule.digits
            }
        })
        metadata_map[rule_name] = {
            "field_name": field_name,
            "expected_ui": expected_ui,
            "extraction_conf": extraction_conf,
            "severity": rule.severity,
            "source_snippet": extracted_field.source_snippet
        }
        
    # 2. Agent Loop
    if items_to_validate:
        system_prompt = VALIDATION_SYSTEM_PROMPT.format(
            rules_json=json.dumps(items_to_validate, indent=2)
        )
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Please validate the document against the provided rules and submit the results using the available tools."}
        ]
        
        while True:
            response = completion(
                model=settings.validation_model,
                max_tokens=2000,
                temperature=0.0, # Deterministic validation
                messages=messages,
                tools=TOOLS
            )
            
            response_message = response.choices[0].message
            # Append assistant message safely
            # litellm expects dictionary format for appending to messages
            assistant_msg = {"role": "assistant"}
            if response_message.content:
                assistant_msg["content"] = response_message.content
            if hasattr(response_message, "tool_calls") and response_message.tool_calls:
                assistant_msg["tool_calls"] = []
                for tc in response_message.tool_calls:
                    assistant_msg["tool_calls"].append({
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    })
            
            messages.append(assistant_msg)
            
            tool_calls = response_message.tool_calls
            if not tool_calls:
                break
                
            final_submission = None
            
            for tool_call in tool_calls:
                func_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments)
                except Exception:
                    args = {}

                if func_name == "evaluate_numeric_tolerance":
                    res = numeric_tolerance_match(
                        args.get("found"),
                        args.get("expected"),
                        args.get("tolerance_pct", 2.0)
                    )
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call.id,
                        "name": func_name, "content": json.dumps(res)
                    })
                elif func_name == "calculate_fuzzy_match":
                    res = fuzzy_match(
                        args.get("found"),
                        args.get("expected"),
                        args.get("threshold", 0.85)
                    )
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call.id,
                        "name": func_name, "content": json.dumps(res)
                    })
                elif func_name == "submit_validation_result":
                    final_submission = args
                    messages.append({
                        "role": "tool", "tool_call_id": tool_call.id,
                        "name": func_name, "content": "Success"
                    })
            
            if final_submission:
                for val in final_submission.get("validations", []):
                    rule_name = val["rule_name"]
                    meta = metadata_map.get(rule_name)
                    if meta:
                        field_validations.append(FieldValidation(
                            field_name=meta["field_name"], document_type=doc_type,
                            found_value=next((i["found_value"] for i in items_to_validate if i["rule_name"] == rule_name), None),
                            expected_value=meta["expected_ui"], result=val["result"],
                            match_confidence=val.get("match_confidence", 1.0),
                            extraction_confidence=meta["extraction_conf"], severity=meta["severity"],
                            reasoning=val["reasoning"], source_snippet=meta["source_snippet"]
                        ))
                break # End agent loop

    # 3. Compute Summary
    critical = sum(1 for v in field_validations if v.result == "mismatch" and v.severity == "critical")
    high = sum(1 for v in field_validations if v.result == "mismatch" and v.severity == "high")
    medium = sum(1 for v in field_validations if v.result == "mismatch" and v.severity == "medium")
    low = sum(1 for v in field_validations if v.result == "mismatch" and v.severity == "low")
    uncertain = sum(1 for v in field_validations if v.result == "uncertain")

    if critical > 0 or high > 0:
        overall_status = "has_mismatches"
    elif uncertain > 0:
        overall_status = "has_uncertain"
    else:
        overall_status = "all_match"

    matches = sum(1 for v in field_validations if v.result == "match")
    total = len(field_validations)
    summary_parts = [f"{matches}/{total} fields match"]
    if critical: summary_parts.append(f"{critical} CRITICAL mismatch(es)")
    if high: summary_parts.append(f"{high} HIGH mismatch(es)")
    if medium: summary_parts.append(f"{medium} MEDIUM mismatch(es)")
    if uncertain: summary_parts.append(f"{uncertain} uncertain")

    processing_time = int((time.time() - start_time) * 1000)

    return ValidationResult(
        document_id=extraction.document_id,
        customer_id=rules.customer_id,
        field_validations=field_validations,
        overall_status=overall_status,
        critical_issues=critical,
        high_issues=high,
        medium_issues=medium,
        low_issues=low,
        summary=". ".join(summary_parts),
        processing_time_ms=processing_time,
    )
