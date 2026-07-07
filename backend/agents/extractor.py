"""Extractor Agent — uses Claude 4 Sonnet with native PDF to extract structured fields.

Input: PDF file path + document type
Output: ExtractionResult with per-field confidence scores and source snippets
"""

import json
import logging
import time
import uuid
import os

from litellm import completion, acompletion

from backend.config.settings import settings
from backend.models.schemas import (
    DOCUMENT_TYPE_MAP,
    ExtractionResult,
    ExtractedField,
)
from backend.prompts.loader import load_prompt
from backend.services.ocr_verifier import verify_extraction
from backend.services.pdf_processor import (
    detect_document_type,
    get_file_name,
    load_pdf_as_base64,
    pdf_to_images,
)

logger = logging.getLogger(__name__)

# Ensure API keys are set in environment for litellm
if settings.anthropic_api_key:
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
if settings.openai_api_key:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key

EXTRACTION_SYSTEM_PROMPT = load_prompt("extraction_system.md")


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
        
    fields["document_quality_score"] = "float 0.0-1.0"
    fields["document_quality_reasoning"] = "string"

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


async def extract_document_async(
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

    user_prompt = load_prompt("extraction_user.md").format(
        document_type=document_type.replace("_", " ").title(),
        field_schema=field_schema,
    )

    # Try native PDF first, fall back to image
    extraction_response = None
    tokens_used = 0
    model_used = settings.extraction_model
    last_error = None

    for attempt in range(settings.max_retries + 1):
        try:
            if attempt == 0:
                # Primary path: native PDF via Claude if applicable
                is_anthropic = model_used.startswith("anthropic/") or "claude" in model_used.lower()
                pdf_base64 = load_pdf_as_base64(pdf_path)
                
                if is_anthropic:
                    content = [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_base64,
                            },
                        },
                        {"type": "text", "text": user_prompt},
                    ]
                else:
                    logger.info("Model is not Anthropic. Converting PDF to images for vision extraction.")
                    page_images = pdf_to_images(pdf_path, dpi=150)
                    content = [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img}"}
                        }
                        for img in page_images
                    ]
                    content.append({"type": "text", "text": user_prompt})

                messages = [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": content}
                ]
                
                response = await acompletion(
                    model=model_used,
                    max_tokens=4096,
                    temperature=settings.extraction_temperature,
                    messages=messages,
                )
            else:
                # Fallback: convert to images at 150 DPI
                logger.info(f"Attempt {attempt + 1}: falling back to image-based extraction")
                page_images = pdf_to_images(pdf_path, dpi=150)
                image_content = [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{img}"
                        }
                    }
                    for img in page_images
                ]
                image_content.append({"type": "text", "text": user_prompt})
                messages = [
                    {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": image_content}
                ]
                response = await acompletion(
                    model=model_used,
                    max_tokens=4096,
                    temperature=settings.extraction_temperature,
                    messages=messages,
                )

            extraction_response = response.choices[0].message.content
            tokens_used = response.usage.prompt_tokens + response.usage.completion_tokens
            break

        except Exception as e:
            last_error = e
            logger.warning(f"Extraction attempt {attempt + 1} failed: {e}")
            if attempt == settings.max_retries:
                logger.error(f"All extraction attempts failed for {pdf_path}")

    # Parse the response into our schema
    quality_score = 1.0
    quality_reasoning = "Clear and readable"
    
    if extraction_response:
        try:
            parsed = _parse_extraction_response(extraction_response, document_type)
            
            # Extract quality metrics
            quality_score = float(parsed.pop("document_quality_score", 1.0))
            quality_reasoning = parsed.pop("document_quality_reasoning", "Clear and readable")
            
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
        document_quality_score=quality_score,
        document_quality_reasoning=quality_reasoning,
    )

    # OCR hallucination verification
    if run_ocr_verification:
        result = verify_extraction(result, pdf_path)

    return result

def extract_document(
    pdf_path: str,
    document_type: str = "auto",
    run_ocr_verification: bool = True,
) -> ExtractionResult:
    """Synchronous wrapper for extract_document_async."""
    import asyncio
    
    # Try to get existing event loop
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
    if loop.is_running():
        # If loop is already running, we can't use run_until_complete directly in the same thread
        # This typically happens if this is called within an existing async context.
        # Ideally, async code should call extract_document_async directly.
        import nest_asyncio
        nest_asyncio.apply()
        
    return asyncio.run(
        extract_document_async(pdf_path, document_type, run_ocr_verification)
    )

