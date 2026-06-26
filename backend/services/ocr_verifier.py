"""OCR-based hallucination verification.

Extracts text from PDF independently and checks if LLM-extracted field values
actually appear in the document. This is the primary defense against hallucination.
"""

import re

from thefuzz import fuzz

from backend.models.schemas import ExtractionResult, ExtractedField
from backend.services.pdf_processor import extract_text_from_pdf


def _normalize(text: str) -> str:
    """Normalize text for comparison — lowercase, collapse whitespace, strip punctuation."""
    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)
    # Normalize common numeric formats: remove commas in numbers
    text = re.sub(r"(\d),(\d)", r"\1\2", text)
    return text


def _value_found_in_text(value: str, ocr_text: str) -> tuple[bool, int]:
    """Check if a value appears in OCR text. Returns (found, fuzzy_score)."""
    norm_value = _normalize(value)
    norm_text = _normalize(ocr_text)

    # Exact substring match
    if norm_value in norm_text:
        return True, 100

    # Fuzzy partial match
    score = fuzz.partial_ratio(norm_value, norm_text)
    return score >= 80, score


def verify_extraction(
    extraction_result: ExtractionResult,
    pdf_path: str,
) -> ExtractionResult:
    """Verify extracted fields against OCR text to catch hallucinations.

    For each field:
    - If value found exactly in OCR text -> confidence unchanged
    - If fuzzy match > 80 -> minor penalty (cap at 0.75)
    - If fuzzy match < 80 -> major penalty (cap at 0.3), flag as potential hallucination
    """
    ocr_text = extract_text_from_pdf(pdf_path)
    extraction_result.raw_ocr_text = ocr_text

    # If OCR returns very little text, it's likely a scanned image —
    # skip verification since we can't verify against empty text
    if len(ocr_text.strip()) < 50:
        return extraction_result

    data = extraction_result.extracted_data
    # Iterate over all fields that are ExtractedField instances
    for field_name in data.model_fields:
        if field_name == "document_type":
            continue
        field: ExtractedField = getattr(data, field_name)
        if field.value is None or field.value.strip() == "":
            continue

        found, score = _value_found_in_text(field.value, ocr_text)

        if found and score == 100:
            # Exact match — no adjustment
            pass
        elif found:
            # Fuzzy match — minor penalty
            field.confidence = min(field.confidence, 0.75)
        else:
            # Not found — potential hallucination
            field.confidence = min(field.confidence, 0.3)
            snippet_note = f"WARNING: Value '{field.value}' not found in document text (fuzzy score: {score})"
            if field.source_snippet:
                field.source_snippet = f"{field.source_snippet} | {snippet_note}"
            else:
                field.source_snippet = snippet_note

    return extraction_result
