"""Pydantic v2 schemas for document extraction output."""

from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class ExtractedField(BaseModel):
    """A single extracted field with confidence and provenance."""
    value: Optional[str] = None
    confidence: float = 0.0
    source_snippet: Optional[str] = None
    page_number: Optional[int] = None


class BillOfLading(BaseModel):
    document_type: Literal["bill_of_lading"] = "bill_of_lading"
    bill_of_lading_number: ExtractedField = Field(default_factory=ExtractedField)
    shipper_name: ExtractedField = Field(default_factory=ExtractedField)
    consignee_name: ExtractedField = Field(default_factory=ExtractedField)
    notify_party: ExtractedField = Field(default_factory=ExtractedField)
    port_of_loading: ExtractedField = Field(default_factory=ExtractedField)
    port_of_discharge: ExtractedField = Field(default_factory=ExtractedField)
    vessel_name: ExtractedField = Field(default_factory=ExtractedField)
    voyage_number: ExtractedField = Field(default_factory=ExtractedField)
    container_number: ExtractedField = Field(default_factory=ExtractedField)
    hs_code: ExtractedField = Field(default_factory=ExtractedField)
    description_of_goods: ExtractedField = Field(default_factory=ExtractedField)
    gross_weight: ExtractedField = Field(default_factory=ExtractedField)
    net_weight: ExtractedField = Field(default_factory=ExtractedField)
    number_of_packages: ExtractedField = Field(default_factory=ExtractedField)
    incoterms: ExtractedField = Field(default_factory=ExtractedField)
    date_of_issue: ExtractedField = Field(default_factory=ExtractedField)
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)
    payment_terms: ExtractedField = Field(default_factory=ExtractedField)


class CommercialInvoice(BaseModel):
    document_type: Literal["commercial_invoice"] = "commercial_invoice"
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)
    invoice_date: ExtractedField = Field(default_factory=ExtractedField)
    seller_name: ExtractedField = Field(default_factory=ExtractedField)
    buyer_name: ExtractedField = Field(default_factory=ExtractedField)
    consignee_name: ExtractedField = Field(default_factory=ExtractedField)
    description_of_goods: ExtractedField = Field(default_factory=ExtractedField)
    hs_code: ExtractedField = Field(default_factory=ExtractedField)
    quantity: ExtractedField = Field(default_factory=ExtractedField)
    unit_price: ExtractedField = Field(default_factory=ExtractedField)
    total_value: ExtractedField = Field(default_factory=ExtractedField)
    currency: ExtractedField = Field(default_factory=ExtractedField)
    gross_weight: ExtractedField = Field(default_factory=ExtractedField)
    net_weight: ExtractedField = Field(default_factory=ExtractedField)
    incoterms: ExtractedField = Field(default_factory=ExtractedField)
    country_of_origin: ExtractedField = Field(default_factory=ExtractedField)
    port_of_loading: ExtractedField = Field(default_factory=ExtractedField)
    port_of_discharge: ExtractedField = Field(default_factory=ExtractedField)
    payment_terms: ExtractedField = Field(default_factory=ExtractedField)


class PackingList(BaseModel):
    document_type: Literal["packing_list"] = "packing_list"
    packing_list_number: ExtractedField = Field(default_factory=ExtractedField)
    invoice_reference: ExtractedField = Field(default_factory=ExtractedField)
    shipper_name: ExtractedField = Field(default_factory=ExtractedField)
    consignee_name: ExtractedField = Field(default_factory=ExtractedField)
    description_of_goods: ExtractedField = Field(default_factory=ExtractedField)
    hs_code: ExtractedField = Field(default_factory=ExtractedField)
    number_of_packages: ExtractedField = Field(default_factory=ExtractedField)
    gross_weight: ExtractedField = Field(default_factory=ExtractedField)
    net_weight: ExtractedField = Field(default_factory=ExtractedField)
    dimensions: ExtractedField = Field(default_factory=ExtractedField)
    container_number: ExtractedField = Field(default_factory=ExtractedField)
    marks_and_numbers: ExtractedField = Field(default_factory=ExtractedField)
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)


class CertificateOfOrigin(BaseModel):
    document_type: Literal["certificate_of_origin"] = "certificate_of_origin"
    certificate_number: ExtractedField = Field(default_factory=ExtractedField)
    exporter_name: ExtractedField = Field(default_factory=ExtractedField)
    consignee_name: ExtractedField = Field(default_factory=ExtractedField)
    country_of_origin: ExtractedField = Field(default_factory=ExtractedField)
    country_of_destination: ExtractedField = Field(default_factory=ExtractedField)
    description_of_goods: ExtractedField = Field(default_factory=ExtractedField)
    hs_code: ExtractedField = Field(default_factory=ExtractedField)
    gross_weight: ExtractedField = Field(default_factory=ExtractedField)
    net_weight: ExtractedField = Field(default_factory=ExtractedField)
    invoice_number: ExtractedField = Field(default_factory=ExtractedField)
    invoice_date: ExtractedField = Field(default_factory=ExtractedField)


# Union of all document types for dynamic parsing
DocumentData = Union[BillOfLading, CommercialInvoice, PackingList, CertificateOfOrigin]

DOCUMENT_TYPE_MAP = {
    "bill_of_lading": BillOfLading,
    "commercial_invoice": CommercialInvoice,
    "packing_list": PackingList,
    "certificate_of_origin": CertificateOfOrigin,
}


class ExtractionResult(BaseModel):
    """Complete result from the Extraction Agent."""
    document_id: str
    document_type: str
    file_name: str
    extracted_data: DocumentData
    raw_ocr_text: Optional[str] = None
    processing_time_ms: int = 0
    model_used: str = ""
    tokens_used: Optional[int] = None
    extraction_timestamp: datetime = Field(default_factory=datetime.utcnow)


# --- Validation schemas ---

class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FieldValidation(BaseModel):
    field_name: str
    found_value: Optional[str] = None
    expected_value: Optional[str] = None
    result: str  # "match" | "mismatch" | "uncertain"
    match_confidence: float = 0.0
    extraction_confidence: float = 0.0
    severity: str = "medium"
    reasoning: Optional[str] = None
    source_snippet: Optional[str] = None


class ValidationResult(BaseModel):
    document_id: str
    customer_id: str
    field_validations: list[FieldValidation] = []
    overall_status: str = "unknown"  # "all_match" | "has_mismatches" | "has_uncertain"
    critical_issues: int = 0
    high_issues: int = 0
    medium_issues: int = 0
    low_issues: int = 0
    summary: str = ""
    processing_time_ms: int = 0


# --- Decision schemas ---

class DecisionResult(BaseModel):
    shipment_id: str
    decision: str  # "approved" | "flagged" | "amendment_required"
    reasoning: str = ""
    draft_email: Optional[str] = None
    flagged_fields: list[str] = []
    overall_confidence: float = 0.0
    processing_time_ms: int = 0
    model_used: Optional[str] = None


# --- Cross-document validation (Part 2) ---

class CrossDocFieldResult(BaseModel):
    field_name: str
    values_by_doc: dict[str, Optional[str]] = {}  # doc_type -> value
    status: str = "match"  # "match" | "mismatch"
    mismatching_documents: list[str] = []
    severity: str = "high"
    master_value: Optional[str] = None  # BOL value (source of truth)


class CrossDocValidationResult(BaseModel):
    shipment_id: str
    field_results: list[CrossDocFieldResult] = []
    has_cross_doc_issues: bool = False
    summary: str = ""
