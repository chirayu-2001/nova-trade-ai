"""Router / Decision Agent — makes routing decisions and drafts emails.

Decision logic is DETERMINISTIC (code-based thresholds, not LLM).
Email drafting uses Claude Sonnet for professional quality.
"""

import json
import logging
import time

import anthropic

from backend.config.settings import settings
from backend.models.schemas import (
    CrossDocValidationResult,
    DecisionResult,
    ValidationResult,
)

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)


def make_decision(validation: ValidationResult) -> tuple[str, list[str]]:
    """Deterministic decision based on validation results.

    Priority order:
    1. Any CRITICAL mismatch -> amendment_required
    2. Any HIGH mismatch -> flagged
    3. Any uncertain field -> flagged
    4. Any field with extraction confidence < threshold -> flagged
    5. Only MEDIUM/LOW mismatches -> approved (with note)
    6. All match -> approved

    Returns: (decision, list_of_flagged_field_names)
    """
    flagged_fields = []

    has_critical = False
    has_high = False
    has_uncertain = False

    for v in validation.field_validations:
        if v.result == "mismatch" and v.severity == "critical":
            has_critical = True
            flagged_fields.append(v.field_name)
        elif v.result == "mismatch" and v.severity == "high":
            has_high = True
            flagged_fields.append(v.field_name)
        elif v.result == "uncertain":
            has_uncertain = True
            flagged_fields.append(v.field_name)
        elif v.result == "mismatch" and v.severity in ("medium", "low"):
            flagged_fields.append(v.field_name)

    if has_critical:
        return "amendment_required", flagged_fields
    elif has_high:
        return "flagged", flagged_fields
    elif has_uncertain:
        return "flagged", flagged_fields
    else:
        return "approved", flagged_fields


def generate_reasoning(
    decision: str,
    validation: ValidationResult,
    cross_doc: CrossDocValidationResult | None = None,
) -> str:
    """Build human-readable reasoning for the decision."""
    parts = []

    if decision == "approved":
        matches = sum(1 for v in validation.field_validations if v.result == "match")
        total = len(validation.field_validations)
        parts.append(f"APPROVED: {matches}/{total} fields match customer requirements.")
        medium_low = [v for v in validation.field_validations if v.result == "mismatch" and v.severity in ("medium", "low")]
        if medium_low:
            parts.append(f"{len(medium_low)} minor issue(s) noted (MEDIUM/LOW severity):")
            for v in medium_low:
                parts.append(f"  - {v.field_name}: found '{v.found_value}', expected '{v.expected_value}'")

    elif decision == "amendment_required":
        critical = [v for v in validation.field_validations if v.result == "mismatch" and v.severity == "critical"]
        high = [v for v in validation.field_validations if v.result == "mismatch" and v.severity == "high"]
        parts.append(f"AMENDMENT REQUIRED: {len(critical)} critical and {len(high)} high-severity issue(s) found.")
        for v in critical + high:
            parts.append(f"  - {v.field_name} ({v.severity.upper()}): found '{v.found_value}', expected '{v.expected_value}'")
            if v.reasoning:
                parts.append(f"    Reason: {v.reasoning}")

    elif decision == "flagged":
        uncertain = [v for v in validation.field_validations if v.result == "uncertain"]
        high = [v for v in validation.field_validations if v.result == "mismatch" and v.severity == "high"]
        parts.append(f"FLAGGED FOR REVIEW: {len(uncertain)} uncertain field(s), {len(high)} high-severity mismatch(es).")
        for v in uncertain:
            parts.append(f"  - {v.field_name}: extraction confidence {v.extraction_confidence:.2f}. Human verification required.")
        for v in high:
            parts.append(f"  - {v.field_name} (HIGH): found '{v.found_value}', expected '{v.expected_value}'")

    # Add cross-document issues if present
    if cross_doc and cross_doc.has_cross_doc_issues:
        parts.append("\nCROSS-DOCUMENT DISCREPANCIES:")
        for f in cross_doc.field_results:
            if f.status == "mismatch":
                values_str = ", ".join(
                    f"{doc}: '{val}'" for doc, val in f.values_by_doc.items() if val
                )
                parts.append(f"  - {f.field_name}: {values_str}")

    return "\n".join(parts)


def draft_amendment_email(
    validation: ValidationResult,
    customer_name: str,
    shipment_id: str,
    cross_doc: CrossDocValidationResult | None = None,
) -> str:
    """Generate a professional amendment request email using Claude Sonnet."""
    # Build discrepancy list
    discrepancies = []
    for v in validation.field_validations:
        if v.result in ("mismatch", "uncertain"):
            discrepancies.append({
                "field": v.field_name.replace("_", " ").title(),
                "found": v.found_value or "Not found",
                "expected": v.expected_value or "N/A",
                "severity": v.severity.upper(),
                "type": "mismatch" if v.result == "mismatch" else "needs verification",
            })

    # Add cross-doc issues
    if cross_doc and cross_doc.has_cross_doc_issues:
        for f in cross_doc.field_results:
            if f.status == "mismatch":
                values_str = "; ".join(
                    f"{doc.replace('_', ' ').title()}: '{val}'"
                    for doc, val in f.values_by_doc.items()
                    if val
                )
                discrepancies.append({
                    "field": f.field_name.replace("_", " ").title(),
                    "found": values_str,
                    "expected": f"Consistent across all documents (master: '{f.master_value}')",
                    "severity": f.severity.upper(),
                    "type": "cross-document inconsistency",
                })

    discrepancy_text = "\n".join(
        f"- {d['field']} [{d['severity']}]: Found \"{d['found']}\" — Expected \"{d['expected']}\" ({d['type']})"
        for d in discrepancies
    )

    prompt = f"""Draft a professional amendment request email from a Cargo Control Group (CG) to a Shipping Unit (SU).

Context:
- Customer: {customer_name}
- Shipment Reference: {shipment_id}
- Number of issues found: {len(discrepancies)}

Discrepancies found:
{discrepancy_text}

Requirements:
1. Professional, clear, and actionable tone
2. List every discrepancy with field name, found value, and expected value
3. Request corrected documents be resubmitted
4. Be ready to send with minimal edits
5. Do NOT include [placeholder] brackets — use the actual values provided
6. Keep it concise — under 300 words

Generate the complete email including Subject line."""

    try:
        response = client.messages.create(
            model=settings.routing_model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.error(f"Email drafting failed: {e}")
        # Fallback template
        return _template_amendment_email(discrepancies, customer_name, shipment_id)


def _template_amendment_email(
    discrepancies: list[dict], customer_name: str, shipment_id: str
) -> str:
    """Fallback template-based email when LLM is unavailable."""
    disc_lines = "\n".join(
        f"  - {d['field']}: Found \"{d['found']}\", Expected \"{d['expected']}\""
        for d in discrepancies
    )
    return f"""Subject: Amendment Request - Shipment {shipment_id} - {customer_name}

Dear Shipping Team,

Following our review of the documents for shipment {shipment_id}, we have identified the following discrepancies that require correction:

{disc_lines}

Please submit corrected documents at your earliest convenience.

Best regards,
Cargo Control Group"""


def draft_approval_email(customer_name: str, shipment_id: str, field_count: int) -> str:
    """Template-based approval email — no LLM needed."""
    return f"""Subject: Documents Approved - Shipment {shipment_id}

Dear Shipping Team,

We have reviewed the documents for shipment {shipment_id} and confirm that all fields meet the requirements for {customer_name}.

All {field_count} validated fields passed successfully.

The approved documents have been forwarded for processing.

Best regards,
Cargo Control Group"""


def route_and_draft(
    validation: ValidationResult,
    customer_name: str,
    shipment_id: str,
    cross_doc: CrossDocValidationResult | None = None,
) -> DecisionResult:
    """Make routing decision and generate appropriate email draft.

    Returns complete DecisionResult with decision, reasoning, and email draft.
    """
    start_time = time.time()

    # Deterministic decision
    decision, flagged_fields = make_decision(validation)

    # Factor in cross-doc issues
    if cross_doc and cross_doc.has_cross_doc_issues:
        critical_cross = any(f.severity == "critical" for f in cross_doc.field_results if f.status == "mismatch")
        if critical_cross:
            decision = "amendment_required"
        elif decision == "approved":
            decision = "flagged"
        for f in cross_doc.field_results:
            if f.status == "mismatch" and f.field_name not in flagged_fields:
                flagged_fields.append(f.field_name)

    # Generate reasoning
    reasoning = generate_reasoning(decision, validation, cross_doc)

    # Generate email draft
    draft_email = None
    model_used = None

    if decision == "amendment_required":
        draft_email = draft_amendment_email(validation, customer_name, shipment_id, cross_doc)
        model_used = settings.routing_model
    elif decision == "approved":
        field_count = len(validation.field_validations)
        draft_email = draft_approval_email(customer_name, shipment_id, field_count)
        # No LLM used — template only

    # Calculate overall confidence
    confidences = [v.extraction_confidence for v in validation.field_validations if v.extraction_confidence > 0]
    overall_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    processing_time = int((time.time() - start_time) * 1000)

    return DecisionResult(
        shipment_id=shipment_id,
        decision=decision,
        reasoning=reasoning,
        draft_email=draft_email,
        flagged_fields=flagged_fields,
        overall_confidence=overall_confidence,
        processing_time_ms=processing_time,
        model_used=model_used,
    )
