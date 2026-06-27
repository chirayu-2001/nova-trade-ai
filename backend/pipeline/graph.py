"""LangGraph pipeline — wires Extractor -> Validator -> Router into a checkpointed graph."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

from langgraph.graph import END, StateGraph

from backend.agents.extractor import extract_document
from backend.agents.router import route_and_draft
from backend.agents.validator import validate_document
from backend.models.database import (
    init_database,
    store_pipeline_checkpoint,
    store_pipeline_result,
)
from backend.models.rules import load_customer_rules
from backend.models.schemas import (
    CrossDocFieldResult,
    CrossDocValidationResult,
    ExtractionResult,
    ValidationResult,
)
from backend.pipeline.state import PipelineState
from backend.pipeline.checkpoint import SQLiteBackedMemorySaver

logger = logging.getLogger(__name__)

MAX_GRAPH_EXTRACTION_RETRIES = 1
StatusCallback = Callable[[dict], None]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Node Functions ---

def extract_node(state: PipelineState) -> dict:
    """Extract structured fields from all documents."""
    timestamps = dict(state.get("timestamps", {}))
    timestamps["extraction_started"] = _now()

    document_paths = state["document_paths"]
    document_types = state.get("document_types", [])

    results = []
    for i, path in enumerate(document_paths):
        doc_type = document_types[i] if i < len(document_types) else "auto"
        try:
            result = extract_document(path, document_type=doc_type)
            results.append(result.model_dump(mode="json"))
        except Exception as e:
            logger.error(f"Extraction failed for {path}: {e}")
            results.append({"error": str(e), "document_path": path})

    timestamps["extraction_completed"] = _now()

    return {
        "extraction_results": results,
        "status": "extracted",
        "timestamps": timestamps,
    }


def retry_extract_node(state: PipelineState) -> dict:
    """Increment retry state before LangGraph loops back to extraction."""
    retry_count = state.get("retry_count", 0) + 1
    timestamps = dict(state.get("timestamps", {}))
    timestamps[f"extraction_retry_{retry_count}"] = _now()

    return {
        "retry_count": retry_count,
        "status": "extracting",
        "timestamps": timestamps,
    }


def validate_node(state: PipelineState) -> dict:
    """Validate extracted fields against customer rules."""
    timestamps = dict(state.get("timestamps", {}))
    timestamps["validation_started"] = _now()

    customer_id = state["customer_id"]
    rules = load_customer_rules(customer_id)

    results = []
    for ext_dict in state.get("extraction_results", []):
        if "error" in ext_dict:
            results.append(ext_dict)
            continue
        try:
            extraction = ExtractionResult.model_validate(ext_dict)
            validation = validate_document(extraction, rules)
            results.append(validation.model_dump(mode="json"))
        except Exception as e:
            logger.error(f"Validation failed: {e}")
            results.append({"error": str(e)})

    timestamps["validation_completed"] = _now()

    return {
        "validation_results": results,
        "status": "validated",
        "timestamps": timestamps,
    }


def cross_validate_node(state: PipelineState) -> dict:
    """Cross-document validation — compare shared fields across all documents."""
    timestamps = dict(state.get("timestamps", {}))
    timestamps["cross_validation_started"] = _now()

    extraction_results = []
    for ext_dict in state.get("extraction_results", []):
        if "error" not in ext_dict:
            extraction_results.append(ExtractionResult.model_validate(ext_dict))

    if len(extraction_results) < 2:
        timestamps["cross_validation_completed"] = _now()
        return {
            "cross_validation_result": CrossDocValidationResult(
                shipment_id=state["shipment_id"],
                summary="Only one document — cross-validation skipped.",
            ).model_dump(mode="json"),
            "status": "cross_validated",
            "timestamps": timestamps,
        }

    # Find the BOL as master document
    master = None
    others = []
    for ext in extraction_results:
        if ext.document_type == "bill_of_lading":
            master = ext
        else:
            others.append(ext)

    if not master:
        master = extraction_results[0]
        others = extraction_results[1:]

    # Fields to cross-validate
    cross_fields = [
        "consignee_name", "hs_code", "gross_weight", "net_weight",
        "incoterms", "port_of_loading", "port_of_discharge", "invoice_number",
    ]

    field_results = []
    has_issues = False

    # Numeric fields need numeric comparison, not fuzzy string match
    numeric_fields = {"gross_weight", "net_weight"}

    for field_name in cross_fields:
        master_field = getattr(master.extracted_data, field_name, None)
        if not master_field or not master_field.value:
            continue

        master_value = master_field.value
        # Use doc_type + index to handle duplicate types
        values_by_doc = {master.document_type: master_value}
        mismatching = []

        for other in others:
            other_field = getattr(other.extracted_data, field_name, None)
            # Build unique key for dict
            doc_key = other.document_type
            if doc_key in values_by_doc:
                doc_key = f"{doc_key}_2"

            if not other_field or not other_field.value:
                values_by_doc[doc_key] = None
                continue

            other_value = other_field.value
            values_by_doc[doc_key] = other_value

            # Compare — numeric fields use numeric comparison
            if field_name in numeric_fields:
                from backend.agents.validator import _extract_numeric
                m_num, _ = _extract_numeric(master_value)
                o_num, _ = _extract_numeric(other_value)
                if m_num is not None and o_num is not None and m_num > 0:
                    pct_diff = abs(m_num - o_num) / m_num * 100
                    if pct_diff > 1.0:  # >1% difference
                        mismatching.append(doc_key)
                elif m_num != o_num:
                    mismatching.append(doc_key)
            else:
                from thefuzz import fuzz
                score = fuzz.token_sort_ratio(
                    master_value.lower().strip(),
                    other_value.lower().strip(),
                ) / 100.0
                if score < 0.85:
                    mismatching.append(doc_key)

        status = "mismatch" if mismatching else "match"
        if mismatching:
            has_issues = True

        severity = "critical" if field_name in ("consignee_name", "hs_code") else "high"

        field_results.append(CrossDocFieldResult(
            field_name=field_name,
            values_by_doc=values_by_doc,
            status=status,
            mismatching_documents=mismatching,
            severity=severity,
            master_value=master_value,
        ))

    mismatches = [f for f in field_results if f.status == "mismatch"]
    summary = (
        f"{len(mismatches)} cross-document discrepancies found."
        if mismatches
        else "All shared fields consistent across documents."
    )

    timestamps["cross_validation_completed"] = _now()

    return {
        "cross_validation_result": CrossDocValidationResult(
            shipment_id=state["shipment_id"],
            field_results=field_results,
            has_cross_doc_issues=has_issues,
            summary=summary,
        ).model_dump(mode="json"),
        "status": "cross_validated",
        "timestamps": timestamps,
    }


def route_node(state: PipelineState) -> dict:
    """Make routing decision and draft email."""
    timestamps = dict(state.get("timestamps", {}))
    timestamps["routing_started"] = _now()

    customer_id = state["customer_id"]
    rules = load_customer_rules(customer_id)

    # Use the first validation result for decision (or aggregate)
    validation_results = state.get("validation_results", [])
    valid_validations = [v for v in validation_results if "error" not in v]

    if not valid_validations:
        timestamps["routing_completed"] = _now()
        return {
            "decision_result": {
                "shipment_id": state["shipment_id"],
                "decision": "flagged",
                "reasoning": "No valid validation results available. Manual review required.",
                "flagged_fields": [],
                "overall_confidence": 0.0,
                "processing_time_ms": 0,
            },
            "status": "decided",
            "timestamps": timestamps,
        }

    # Aggregate: combine all validation results
    field_to_vals = {}
    for v_dict in valid_validations:
        v = ValidationResult.model_validate(v_dict)
        for fv in v.field_validations:
            field_to_vals.setdefault(fv.field_name, []).append(fv)
            
    combined_validations = []
    for field_name, fvs in field_to_vals.items():
        def severity_score(fv):
            if fv.result == "match": return 0
            if fv.result == "uncertain": return 1
            if fv.severity == "low": return 2
            if fv.severity == "medium": return 3
            if fv.severity == "high": return 4
            if fv.severity == "critical": return 5
            return 0
            
        worst_fv = max(fvs, key=severity_score)
        combined_validations.append(worst_fv)

    # Recompute summary stats
    critical = sum(1 for v in combined_validations if v.result == "mismatch" and v.severity == "critical")
    high = sum(1 for v in combined_validations if v.result == "mismatch" and v.severity == "high")
    medium = sum(1 for v in combined_validations if v.result == "mismatch" and v.severity == "medium")
    low = sum(1 for v in combined_validations if v.result == "mismatch" and v.severity == "low")
    
    if critical > 0 or high > 0:
        overall_status = "has_mismatches"
    elif any(v.result == "uncertain" for v in combined_validations):
        overall_status = "has_uncertain"
    else:
        overall_status = "all_match"

    aggregated_validation = ValidationResult(
        document_id="aggregated",
        customer_id=customer_id,
        field_validations=combined_validations,
        overall_status=overall_status,
        critical_issues=critical,
        high_issues=high,
        medium_issues=medium,
        low_issues=low,
        summary="Aggregated",
        processing_time_ms=0,
    )

    cross_doc = None
    cross_doc_dict = state.get("cross_validation_result")
    if cross_doc_dict:
        cross_doc = CrossDocValidationResult.model_validate(cross_doc_dict)

    # Identify low quality documents
    low_quality_docs = []
    for ext_dict in state.get("extraction_results", []):
        if "error" not in ext_dict:
            score = ext_dict.get("document_quality_score", 1.0)
            if score < 0.6:
                low_quality_docs.append({
                    "file_name": ext_dict.get("file_name", "Unknown Document"),
                    "score": score,
                    "reasoning": ext_dict.get("document_quality_reasoning", "Unreadable scan"),
                })

    decision = route_and_draft(
        aggregated_validation,
        rules.customer_name,
        state["shipment_id"],
        cross_doc,
        low_quality_docs=low_quality_docs,
    )

    timestamps["routing_completed"] = _now()

    return {
        "decision_result": decision.model_dump(mode="json"),
        "status": "decided",
        "timestamps": timestamps,
    }


def store_node(state: PipelineState) -> dict:
    """Persist results to database."""
    timestamps = dict(state.get("timestamps", {}))
    timestamps["stored"] = _now()

    try:
        # Set status to "stored" before persisting so DB has the correct value
        state_to_store = dict(state)
        state_to_store["status"] = "stored"
        store_pipeline_result(state_to_store)
    except Exception as e:
        logger.error(f"Failed to store results: {e}")

    return {
        "status": "stored",
        "timestamps": timestamps,
    }


def error_node(state: PipelineState) -> dict:
    """Handle pipeline errors."""
    errors = [
        r.get("error", "Unknown extraction error")
        for r in state.get("extraction_results", [])
        if isinstance(r, dict) and "error" in r
    ]
    return {
        "status": "error",
        "error": "; ".join(errors) if errors else state.get("error") or "Pipeline failed",
    }


# --- Graph Definition ---

def should_retry(state: PipelineState) -> str:
    """Check if extraction produced errors that warrant retry."""
    results = state.get("extraction_results", [])
    has_errors = any("error" in r for r in results)
    retry_count = state.get("retry_count", 0)

    if has_errors and retry_count < MAX_GRAPH_EXTRACTION_RETRIES:
        return "retry"
    elif has_errors and all("error" in r for r in results):
        return "fail"
    return "continue"


def build_graph():
    """Build and compile the LangGraph pipeline."""
    builder = StateGraph(PipelineState)

    builder.add_node("extract", extract_node)
    builder.add_node("retry_extract", retry_extract_node)
    builder.add_node("validate", validate_node)
    builder.add_node("cross_validate", cross_validate_node)
    builder.add_node("route", route_node)
    builder.add_node("store", store_node)
    builder.add_node("error", error_node)

    builder.set_entry_point("extract")

    builder.add_conditional_edges("extract", should_retry, {
        "retry": "retry_extract",
        "continue": "validate",
        "fail": "error",
    })
    builder.add_edge("retry_extract", "extract")
    builder.add_edge("validate", "cross_validate")
    builder.add_edge("cross_validate", "route")
    builder.add_edge("route", "store")
    builder.add_edge("store", END)
    builder.add_edge("error", END)

    checkpointer = SQLiteBackedMemorySaver()
    graph = builder.compile(checkpointer=checkpointer)
    return graph


# Module-level graph instance
pipeline_graph = build_graph()


def run_pipeline(
    document_paths: list[str],
    customer_id: str,
    document_types: list[str] | None = None,
    shipment_id: str | None = None,
    status_callback: StatusCallback | None = None,
) -> PipelineState:
    """Run the full pipeline on one or more documents.

    Args:
        document_paths: List of PDF file paths
        customer_id: Customer ID for rule loading
        document_types: Optional list of doc types (parallel to paths)
        shipment_id: Optional shipment ID (auto-generated if not provided)

    Returns:
        Final PipelineState with all results
    """
    if not shipment_id:
        shipment_id = f"SHP-{uuid.uuid4().hex[:8].upper()}"

    if not document_types:
        document_types = ["auto"] * len(document_paths)

    init_database()

    initial_state: PipelineState = {
        "document_paths": document_paths,
        "document_types": document_types,
        "customer_id": customer_id,
        "shipment_id": shipment_id,
        "extraction_results": [],
        "validation_results": [],
        "cross_validation_result": None,
        "decision_result": None,
        "status": "extracting",
        "error": None,
        "retry_count": 0,
        "timestamps": {"started": _now()},
    }

    config = {"configurable": {"thread_id": shipment_id}}
    store_pipeline_checkpoint(initial_state)
    if status_callback:
        status_callback(initial_state)

    final_state: PipelineState = initial_state
    for state in pipeline_graph.stream(
        initial_state,
        config=config,
        stream_mode="values",
    ):
        if not isinstance(state, dict):
            continue
        final_state = state
        store_pipeline_checkpoint(final_state)
        if status_callback:
            status_callback(final_state)

    return final_state
