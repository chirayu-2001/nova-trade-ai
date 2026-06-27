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


def _is_collided(norm_value: str, norm_text: str) -> bool:
    """Detect whether an exact-matching value is jammed against neighboring characters.

    Overlapping table columns (e.g. a description bleeding into a weight column) produce
    jumbled text like "gearbox8750kgslies". The value's leading digit/letter is still present,
    so a naive substring match succeeds, but the value is actually merged with adjacent text.
    We flag that as a collision so confidence can be penalized.
    """
    # Look at the first alphanumeric token of the value (e.g. "8750" from "8750 kgs").
    m = re.search(r"[a-z0-9]+", norm_value)
    if not m:
        return False
    token = m.group(0)
    for occ in re.finditer(re.escape(token), norm_text):
        before = norm_text[occ.start() - 1] if occ.start() > 0 else " "
        after = norm_text[occ.end()] if occ.end() < len(norm_text) else " "
        # Clean if at least one side is a boundary (space/punct). Collision only if BOTH
        # sides are glued to other alphanumeric characters.
        if not (before.isalnum() and after.isalnum()):
            return False
    return True


def _value_found_in_text(value: str, ocr_text: str) -> tuple[bool, int, bool]:
    """Check if a value appears in OCR text. Returns (found, fuzzy_score, collided)."""
    norm_value = _normalize(value)
    norm_text = _normalize(ocr_text)

    # Exact substring match
    if norm_value in norm_text:
        return True, 100, _is_collided(norm_value, norm_text)

    # Fuzzy partial match
    score = fuzz.partial_ratio(norm_value, norm_text)
    return score >= 80, score, False


def verify_extraction(
    extraction_result: ExtractionResult,
    pdf_path: str,
) -> ExtractionResult:
    """Verify extracted fields against OCR text to catch hallucinations.

    For each field:
    - If value found exactly AND cleanly (at word boundaries) -> confidence unchanged
    - If value found exactly but collided/merged with neighboring text -> cap at 0.5
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

        found, score, collided = _value_found_in_text(field.value, ocr_text)

        if found and score == 100 and not collided:
            # Clean exact match — no adjustment
            pass
        elif found and collided:
            # Value is present but merged with adjacent text (overlapping columns) —
            # the reading is ambiguous, so cap confidence and surface the collision.
            field.confidence = min(field.confidence, 0.5)
            note = f"WARNING: Value '{field.value}' overlaps adjacent text in the document (possible column collision)"
            field.source_snippet = f"{field.source_snippet} | {note}" if field.source_snippet else note
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