"""Validator Agent — compares extracted fields against customer rules.

Mostly deterministic matching with LLM fallback for semantic cases.
70% of validation is code-based, 30% uses Claude Haiku for edge cases.
"""

import logging
import re
import time
from typing import Optional

import anthropic
from thefuzz import fuzz

from backend.config.settings import settings
from backend.models.rules import CustomerRuleSet, FieldRule, load_customer_rules
from backend.models.schemas import (
    ExtractionResult,
    ExtractedField,
    FieldValidation,
    ValidationResult,
)

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

# --- Field Matching Strategies ---

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
    # Extract unit
    unit_match = re.search(r"(KG|MT|LBS|PCS|CTNS|CBM|SETS|NOS)", text.upper())
    unit = unit_match.group(1) if unit_match else None

    # Extract number — handle both "4,250" and "4.250" (European)
    num_str = re.sub(r"[^\d.,\-]", "", text)
    if not num_str:
        return None, unit

    # Heuristic: if comma is used as thousands separator (e.g., "4,250")
    # vs decimal separator (e.g., "4,25" in European format)
    if "," in num_str and "." in num_str:
        # Both present: assume comma=thousands, dot=decimal (US format)
        num_str = num_str.replace(",", "")
    elif "," in num_str:
        parts = num_str.split(",")
        if len(parts[-1]) == 3:
            # Likely thousands separator: 4,250
            num_str = num_str.replace(",", "")
        else:
            # Likely decimal separator: 4,25
            num_str = num_str.replace(",", ".")

    try:
        return float(num_str), unit
    except ValueError:
        return None, unit


def exact_match(found: str, expected: str, case_sensitive: bool = False) -> tuple[str, float]:
    """Case-insensitive string equality."""
    if case_sensitive:
        match = found.strip() == expected.strip()
    else:
        match = found.strip().lower() == expected.strip().lower()
    return ("match" if match else "mismatch", 1.0)


def fuzzy_match(found: str, expected: str, threshold: float = 0.85) -> tuple[str, float]:
    """Jaro-Winkler / token sort fuzzy matching."""
    token_score = fuzz.token_sort_ratio(found.lower(), expected.lower()) / 100.0
    partial_score = fuzz.partial_ratio(found.lower(), expected.lower()) / 100.0
    score = max(token_score, partial_score)

    if score >= threshold:
        return ("match", score)
    elif score >= threshold - 0.10:
        return ("uncertain", score)
    else:
        return ("mismatch", score)


def numeric_tolerance_match(
    found: str, expected: str, tolerance_pct: float = 2.0
) -> tuple[str, float]:
    """Numeric comparison with unit conversion and tolerance."""
    found_num, found_unit = _extract_numeric(found)
    expected_num, expected_unit = _extract_numeric(expected)

    if found_num is None or expected_num is None:
        return ("uncertain", 0.5)

    # Unit conversion if needed
    if found_unit and expected_unit and found_unit != expected_unit:
        conversion = UNIT_CONVERSIONS.get((found_unit, expected_unit))
        if conversion:
            found_num = found_num * conversion
        else:
            return ("uncertain", 0.5)

    if expected_num == 0:
        return ("match" if found_num == 0 else "mismatch", 1.0)

    pct_diff = abs(found_num - expected_num) / abs(expected_num) * 100

    if pct_diff <= tolerance_pct:
        return ("match", max(0.0, 1.0 - pct_diff / 100.0))
    elif pct_diff <= tolerance_pct * 2:
        return ("uncertain", 0.5)
    else:
        return ("mismatch", max(0.0, 1.0 - pct_diff / 100.0))


def regex_match(found: str, pattern: str) -> tuple[str, float]:
    """Regex pattern match."""
    if re.match(pattern, found.strip()):
        return ("match", 1.0)
    return ("mismatch", 1.0)


def format_match(found: str, pattern: str, digits: Optional[int] = None) -> tuple[str, float]:
    """Format validation — e.g., HS code must be ####.##.## format."""
    if not found:
        return ("mismatch", 1.0)

    # Check digit count for HS codes
    if digits:
        found_digits = re.sub(r"[^\d]", "", found)
        if len(found_digits) != digits:
            return ("mismatch", 1.0)

    # Convert pattern ####.##.## to regex
    if pattern:
        regex = pattern.replace("#", r"\d").replace(".", r"\.")
        if re.match(regex, found.strip()):
            return ("match", 1.0)
        return ("mismatch", 0.9)

    return ("match", 1.0)


def exact_prefix_match(found: str, expected: str, prefix_length: int) -> tuple[str, float]:
    """First N characters must match (for HS codes)."""
    norm_found = re.sub(r"[^\d]", "", found)
    norm_expected = re.sub(r"[^\d]", "", expected)
    if norm_found[:prefix_length] == norm_expected[:prefix_length]:
        return ("match", 1.0)
    return ("mismatch", 1.0)


def semantic_match(found: str, expected: str) -> tuple[str, float]:
    """LLM-based semantic matching — expensive, used as last resort."""
    try:
        response = client.messages.create(
            model=settings.validation_model,
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"""Do these two values refer to the same entity in a trade document context?
Value 1: "{found}"
Value 2: "{expected}"
Consider abbreviations, formatting differences, and common trade terminology.
Respond with ONLY a JSON object: {{"match": true/false, "confidence": 0.0-1.0, "reasoning": "brief explanation"}}"""
            }],
        )
        import json
        text = response.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        result = json.loads(text)
        is_match = result.get("match", False)
        confidence = float(result.get("confidence", 0.5))
        return ("match" if is_match else "mismatch", confidence)
    except Exception as e:
        logger.warning(f"Semantic match failed: {e}")
        return ("uncertain", 0.5)


def match_field(found_value: str, rule: FieldRule) -> tuple[str, float, str]:
    """Dispatch to the correct matcher based on rule match_type.

    Returns: (result, confidence, reasoning)
    """
    expected = rule.expected or ""
    match_type = rule.match_type

    if match_type == "exact":
        result, conf = exact_match(found_value, expected, rule.case_sensitive)
        reasoning = f"Exact match: '{found_value}' vs '{expected}'"
    elif match_type == "fuzzy":
        result, conf = fuzzy_match(found_value, expected, rule.threshold)
        reasoning = f"Fuzzy match (score={conf:.2f}, threshold={rule.threshold}): '{found_value}' vs '{expected}'"
    elif match_type == "numeric_tolerance":
        result, conf = numeric_tolerance_match(found_value, expected, rule.tolerance_pct)
        reasoning = f"Numeric tolerance (±{rule.tolerance_pct}%): '{found_value}' vs '{expected}'"
    elif match_type == "regex":
        result, conf = regex_match(found_value, rule.pattern or "")
        reasoning = f"Regex match against pattern '{rule.pattern}': '{found_value}'"
    elif match_type == "format":
        result, conf = format_match(found_value, rule.pattern or "", rule.digits)
        reasoning = f"Format validation ({rule.pattern}, {rule.digits} digits): '{found_value}'"
    elif match_type == "exact_prefix":
        result, conf = exact_prefix_match(found_value, expected, rule.prefix_length or 6)
        reasoning = f"Prefix match ({rule.prefix_length} chars): '{found_value}' vs '{expected}'"
    elif match_type == "semantic":
        result, conf = semantic_match(found_value, expected)
        reasoning = f"Semantic match: '{found_value}' vs '{expected}'"
    elif match_type == "contains":
        result = "match" if expected.lower() in found_value.lower() else "mismatch"
        conf = 1.0
        reasoning = f"Contains check: '{expected}' in '{found_value}'"
    elif match_type in ("cross_document_consistent", "present_on_all"):
        # These are handled at the cross-document level, skip per-doc validation
        return "match", 1.0, "Cross-document rule — validated separately"
    else:
        return "uncertain", 0.5, f"Unknown match type: {match_type}"

    return result, conf, reasoning


# --- Main Validator ---

def validate_document(
    extraction: ExtractionResult,
    rules: CustomerRuleSet,
) -> ValidationResult:
    """Validate extracted fields against customer rules.

    For each rule:
    1. Find the corresponding extracted field
    2. Apply the appropriate matching strategy
    3. Build a FieldValidation result

    CRITICAL: If extraction confidence < threshold, mark as "uncertain", never "match".
    """
    start_time = time.time()

    field_validations = []
    extracted_data = extraction.extracted_data

    for rule_name, rule in rules.rules.items():
        # Map rule names to extraction field names
        # Rules might use slightly different names, so we try direct match first
        field_name = rule.field if rule.field else rule_name

        # Try to get the field from extracted data
        extracted_field = None
        if hasattr(extracted_data, field_name):
            extracted_field = getattr(extracted_data, field_name)
        elif hasattr(extracted_data, rule_name):
            extracted_field = getattr(extracted_data, rule_name)
        else:
            # Try common mappings
            name_mappings = {
                "incoterm": "incoterms",
                "incoterms": "incoterms",
                "hs_code_format": "hs_code",
                "weight_cross_doc": "gross_weight",
                "invoice_on_all_docs": "invoice_number",
            }
            mapped = name_mappings.get(rule_name)
            if mapped and hasattr(extracted_data, mapped):
                extracted_field = getattr(extracted_data, mapped)
                field_name = mapped

        # Handle missing fields
        if extracted_field is None or not isinstance(extracted_field, ExtractedField):
            if rule.required:
                field_validations.append(FieldValidation(
                    field_name=rule_name,
                    found_value=None,
                    expected_value=rule.expected,
                    result="mismatch",
                    match_confidence=1.0,
                    extraction_confidence=0.0,
                    severity=rule.severity,
                    reasoning=f"Required field '{rule_name}' not found in extraction",
                ))
            continue

        found_value = extracted_field.value
        extraction_conf = extracted_field.confidence

        # If field is empty/None
        if not found_value or found_value.strip() == "":
            if rule.required:
                field_validations.append(FieldValidation(
                    field_name=field_name,
                    found_value=None,
                    expected_value=rule.expected,
                    result="mismatch",
                    match_confidence=1.0,
                    extraction_confidence=extraction_conf,
                    severity=rule.severity,
                    reasoning=f"Required field '{field_name}' has no value",
                    source_snippet=extracted_field.source_snippet,
                ))
            continue

        # CRITICAL: Low extraction confidence -> uncertain, never auto-match
        if extraction_conf < settings.confidence_threshold:
            field_validations.append(FieldValidation(
                field_name=field_name,
                found_value=found_value,
                expected_value=rule.expected,
                result="uncertain",
                match_confidence=0.0,
                extraction_confidence=extraction_conf,
                severity=rule.severity,
                reasoning=f"Extraction confidence too low ({extraction_conf:.2f} < {settings.confidence_threshold}). Human verification required.",
                source_snippet=extracted_field.source_snippet,
            ))
            continue

        # Apply matching strategy
        result, match_conf, reasoning = match_field(found_value, rule)

        field_validations.append(FieldValidation(
            field_name=field_name,
            found_value=found_value,
            expected_value=rule.expected,
            result=result,
            match_confidence=match_conf,
            extraction_confidence=extraction_conf,
            severity=rule.severity,
            reasoning=reasoning,
            source_snippet=extracted_field.source_snippet,
        ))

    # Compute summary
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
    if critical:
        summary_parts.append(f"{critical} CRITICAL mismatch(es)")
    if high:
        summary_parts.append(f"{high} HIGH mismatch(es)")
    if medium:
        summary_parts.append(f"{medium} MEDIUM mismatch(es)")
    if uncertain:
        summary_parts.append(f"{uncertain} uncertain (low confidence)")

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
