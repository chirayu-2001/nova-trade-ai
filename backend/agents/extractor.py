"""Extractor Agent — uses Claude 4 Sonnet with native PDF to extract structured fields.

Input: PDF file path + document type
Output: ExtractionResult with per-field confidence scores and source snippets
"""

import json
import logging
import time
import uuid

import anthropic

from backend.config.settings import settings
from backend.models.schemas import (
    DOCUMENT_TYPE_MAP,
    ExtractionResult,
    ExtractedField,
)
from backend.services.ocr_verifier import verify_extraction
from backend.services.pdf_processor import (
    detect_document_type,
    get_file_name,
    load_pdf_as_base64,
    pdf_to_images,
)

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

EXTRACTION_SYSTEM_PROMPT = """You are a trade document extraction specialist. You extract structured data from trade documents (Bills of Lading, Commercial Invoices, Packing Lists, Certificates of Origin) with high accuracy.

CRITICAL RULES:
1. Only extract values that are EXPLICITLY visible in the document. Never guess or infer.
2. If a field is not present in the document, set value to null and confidence to 0.0.
3. For each field, quote the EXACT text snippet from the document where you found the value in the source_snippet field.
4. Rate your confidence 0.0-1.0 for each field:
   - 0.9-1.0 = clearly printed, unambiguous, easy to read
   - 0.7-0.89 = readable but some ambiguity (small font, partial occlusion)
   - 0.4-0.69 = hard to read, partially guessing from context
   - 0.0-0.39 = very uncertain or not found
5. For tabular data, pay attention to column headers and row alignment.
6. For weights, include the unit (KG, MT, LBS).
7. For HS codes, extract the full code including all digits and dots.
8. For Incoterms, include the location if specified (e.g., "FOB Shanghai", "CIF Hamburg").

Return ONLY valid JSON matching the schema provided. No markdown, no explanation, just the JSON object."""


def _build_field_schema(doc_type: str) -> str:
    """Generate the expected JSON schema description for a document type."""
    model_class = DOCUMENT_TYPE_MAP.get(doc_type)
    if not model_class:
        return ""

    fields = {}
    for name, field_info in model_class.model_fields.items():
        if name == "document_type":
            continue
        fields[name] = {
            "value": "string or null",
            "confidence": "float 0.0-1.0",
            "source_snippet": "exact text from document or null",
            "page_number": "int or null",
        }

    return json.dumps(fields, indent=2)


def _parse_extraction_response(response_text: str, doc_type: str) -> dict:
    """Parse LLM response into field dict, handling various JSON formats."""
    text = response_text.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()
        if text.startswith("json"):
            text = text[4:].strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON object from the text (LLM may add extra text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    # Try fixing common issues: trailing commas, unescaped quotes in values
    import re
    cleaned = text[start:end + 1] if start != -1 and end != -1 else text
    # Remove trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)
    # Try to fix unescaped newlines in string values
    cleaned = cleaned.replace("\n", "\\n")
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    raise json.JSONDecodeError("Could not parse LLM response as JSON", text, 0)


def extract_document(
    pdf_path: str,
    document_type: str = "auto",
    run_ocr_verification: bool = True,
) -> ExtractionResult:
    """Extract structured fields from a trade document PDF.

    Args:
        pdf_path: Path to the PDF file
        document_type: Document type or "auto" to detect
        run_ocr_verification: Whether to verify against OCR text

    Returns:
        ExtractionResult with all extracted fields, confidence scores, and provenance
    """
    start_time = time.time()

    # Detect document type if needed
    if document_type == "auto" or document_type == "unknown":
        document_type = detect_document_type(pdf_path)
        if document_type == "unknown":
            document_type = "bill_of_lading"  # Default fallback
            logger.warning(f"Could not detect document type for {pdf_path}, defaulting to bill_of_lading")

    model_class = DOCUMENT_TYPE_MAP.get(document_type)
    if not model_class:
        raise ValueError(f"Unknown document type: {document_type}")

    doc_id = str(uuid.uuid4())[:8]
    field_schema = _build_field_schema(document_type)

    user_prompt = f"""You are extracting a {document_type.replace('_', ' ').title()}.

Extract ALL of the following fields from this document. Return a JSON object where each key is a field name and each value is an object with "value", "confidence", "source_snippet", and "page_number".

Fields to extract:
{field_schema}

Return ONLY the JSON object. No markdown formatting."""

    # Try native PDF first, fall back to image
    extraction_response = None
    tokens_used = 0
    model_used = settings.extraction_model
    last_error = None

    for attempt in range(settings.max_retries + 1):
        try:
            if attempt == 0:
                # Primary path: native PDF via Claude
                pdf_base64 = load_pdf_as_base64(pdf_path)
                response = client.messages.create(
                    model=model_used,
                    max_tokens=4096,
                    messages=[{
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64,
                                },
                            },
                            {"type": "text", "text": user_prompt},
                        ],
                    }],
                    system=EXTRACTION_SYSTEM_PROMPT,
                )
            else:
                # Fallback: convert to images at 150 DPI
                logger.info(f"Attempt {attempt + 1}: falling back to image-based extraction")
                page_images = pdf_to_images(pdf_path, dpi=150)
                image_content = [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img,
                        },
                    }
                    for img in page_images
                ]
                image_content.append({"type": "text", "text": user_prompt})
                response = client.messages.create(
                    model=model_used,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": image_content}],
                    system=EXTRACTION_SYSTEM_PROMPT,
                )

            extraction_response = response.content[0].text
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
            break

        except Exception as e:
            last_error = e
            logger.warning(f"Extraction attempt {attempt + 1} failed: {e}")
            if attempt == settings.max_retries:
                logger.error(f"All extraction attempts failed for {pdf_path}")

    # Parse the response into our schema
    if extraction_response:
        try:
            parsed = _parse_extraction_response(extraction_response, document_type)
            # Build the Pydantic model from parsed fields
            field_data = {}
            for field_name in model_class.model_fields:
                if field_name == "document_type":
                    continue
                if field_name in parsed and isinstance(parsed[field_name], dict):
                    field_data[field_name] = ExtractedField(
                        value=parsed[field_name].get("value"),
                        confidence=float(parsed[field_name].get("confidence", 0.0)),
                        source_snippet=parsed[field_name].get("source_snippet"),
                        page_number=parsed[field_name].get("page_number"),
                    )
                else:
                    field_data[field_name] = ExtractedField()

            extracted_data = model_class(**field_data)

        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"Failed to parse extraction response: {e}")
            # Return empty extraction with zero confidence
            extracted_data = model_class()
    else:
        extracted_data = model_class()

    processing_time = int((time.time() - start_time) * 1000)

    result = ExtractionResult(
        document_id=doc_id,
        document_type=document_type,
        file_name=get_file_name(pdf_path),
        extracted_data=extracted_data,
        processing_time_ms=processing_time,
        model_used=model_used,
        tokens_used=tokens_used,
    )

    # OCR hallucination verification
    if run_ocr_verification:
        result = verify_extraction(result, pdf_path)

    return result
