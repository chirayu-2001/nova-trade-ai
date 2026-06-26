"""PDF processing service using PyMuPDF (fitz).

Two code paths:
1. Native PDF base64 — for Claude/Gemini that accept PDFs directly (preferred)
2. Image conversion at 150 DPI — fallback for GPT-4o or degraded docs
"""

import base64
import os

import fitz  # PyMuPDF


def load_pdf_as_base64(pdf_path: str) -> str:
    """Read PDF as raw bytes and base64-encode for Claude's native PDF support."""
    with open(pdf_path, "rb") as f:
        return base64.standard_b64encode(f.read()).decode("utf-8")


def pdf_to_images(pdf_path: str, dpi: int = 150) -> list[str]:
    """Convert PDF pages to base64-encoded PNG images at specified DPI.

    150 DPI is the sweet spot — 72 loses small text, 300 doubles token cost.
    """
    doc = fitz.open(pdf_path)
    images = []
    scale = dpi / 72.0
    matrix = fitz.Matrix(scale, scale)
    for page in doc:
        pix = page.get_pixmap(matrix=matrix)
        img_bytes = pix.tobytes("png")
        b64 = base64.standard_b64encode(img_bytes).decode("utf-8")
        images.append(b64)
    doc.close()
    return images


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract embedded text from PDF using PyMuPDF.

    This provides OCR ground truth for hallucination verification.
    For digital PDFs, returns the embedded text.
    For pure scanned images, returns empty or minimal text.
    """
    doc = fitz.open(pdf_path)
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text("text"))
    doc.close()
    return "\n".join(text_parts)


def detect_document_type(pdf_path: str) -> str:
    """Heuristic document type detection from first-page text.

    Returns: 'bill_of_lading', 'commercial_invoice', 'packing_list',
             'certificate_of_origin', or 'unknown'
    """
    text = extract_text_from_pdf(pdf_path).upper()[:2000]  # First ~2 pages
    # Check the first line / title area (most reliable)
    first_200 = text[:200]

    # Check specific doc titles first (in first 200 chars for priority)
    if "COMMERCIAL INVOICE" in first_200:
        return "commercial_invoice"
    elif "PACKING LIST" in first_200:
        return "packing_list"
    elif "CERTIFICATE OF ORIGIN" in first_200:
        return "certificate_of_origin"
    elif "BILL OF LADING" in first_200:
        return "bill_of_lading"

    # Fallback: check full text
    if "COMMERCIAL INVOICE" in text:
        return "commercial_invoice"
    elif "PACKING LIST" in text:
        return "packing_list"
    elif "CERTIFICATE OF ORIGIN" in text:
        return "certificate_of_origin"
    elif "BILL OF LADING" in text or "B/L" in text:
        return "bill_of_lading"
    return "unknown"


def get_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    count = len(doc)
    doc.close()
    return count


def get_file_name(pdf_path: str) -> str:
    return os.path.basename(pdf_path)
