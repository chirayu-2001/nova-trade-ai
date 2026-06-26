"""LangGraph pipeline state schema."""

from typing import Any, Optional, TypedDict


class PipelineState(TypedDict, total=False):
    # Input
    document_paths: list[str]
    document_types: list[str]  # Parallel to document_paths
    customer_id: str
    shipment_id: str

    # Stage outputs (serialized as dicts for LangGraph compatibility)
    extraction_results: list[dict[str, Any]]
    validation_results: list[dict[str, Any]]
    cross_validation_result: Optional[dict[str, Any]]
    decision_result: Optional[dict[str, Any]]

    # Pipeline metadata
    status: str  # incoming | extracting | validating | cross_validating | routing | decided | stored | error
    error: Optional[str]
    retry_count: int
    timestamps: dict[str, str]
