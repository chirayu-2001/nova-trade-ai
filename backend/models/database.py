"""SQLite database layer — stores pipeline results for querying."""

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from backend.config.settings import settings

_DB_PATH = None


def _get_db_path() -> str:
    global _DB_PATH
    if _DB_PATH:
        return _DB_PATH
    _DB_PATH = settings.database_path
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    db_path = _get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_database():
    """Create tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS shipments (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            customer_name TEXT,
            status TEXT NOT NULL DEFAULT 'incoming',
            decision TEXT,
            decision_reasoning TEXT,
            draft_email TEXT,
            overall_confidence REAL,
            document_count INTEGER DEFAULT 0,
            cross_validation_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            shipment_id TEXT NOT NULL REFERENCES shipments(id),
            document_type TEXT NOT NULL,
            file_path TEXT,
            file_name TEXT,
            extracted_json TEXT,
            raw_ocr_text TEXT,
            extraction_confidence_avg REAL,
            model_used TEXT,
            tokens_used INTEGER,
            processing_time_ms INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS validations (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL REFERENCES documents(id),
            shipment_id TEXT NOT NULL REFERENCES shipments(id),
            document_type TEXT,
            field_name TEXT NOT NULL,
            found_value TEXT,
            expected_value TEXT,
            match_result TEXT NOT NULL,
            match_confidence REAL,
            extraction_confidence REAL,
            severity TEXT,
            reasoning TEXT,
            source_snippet TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_shipments_customer ON shipments(customer_id);
        CREATE INDEX IF NOT EXISTS idx_shipments_status ON shipments(status);
        CREATE INDEX IF NOT EXISTS idx_shipments_decision ON shipments(decision);
        CREATE INDEX IF NOT EXISTS idx_documents_shipment ON documents(shipment_id);
        CREATE INDEX IF NOT EXISTS idx_validations_shipment ON validations(shipment_id);
        CREATE INDEX IF NOT EXISTS idx_validations_result ON validations(match_result);

        CREATE TABLE IF NOT EXISTS pipeline_checkpoints (
            shipment_id TEXT PRIMARY KEY,
            customer_id TEXT,
            status TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            error TEXT,
            state_json TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_pipeline_checkpoints_status
            ON pipeline_checkpoints(status);

        CREATE TABLE IF NOT EXISTS langgraph_checkpoints (
            namespace TEXT PRIMARY KEY,
            payload BLOB NOT NULL,
            updated_at TIMESTAMP NOT NULL
        );
    """)
    conn.commit()
    conn.close()


def store_pipeline_checkpoint(state: dict[str, Any]):
    """Persist the latest pipeline state for crash recovery and observability."""
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO pipeline_checkpoints
            (shipment_id, customer_id, status, retry_count, error, state_json, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(shipment_id) DO UPDATE SET
                customer_id = excluded.customer_id,
                status = excluded.status,
                retry_count = excluded.retry_count,
                error = excluded.error,
                state_json = excluded.state_json,
                updated_at = excluded.updated_at
            """,
            (
                state.get("shipment_id"),
                state.get("customer_id"),
                state.get("status", "unknown"),
                state.get("retry_count", 0),
                state.get("error"),
                json.dumps(state, default=str),
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_pipeline_checkpoint(shipment_id: str) -> Optional[dict]:
    """Return the latest durable pipeline checkpoint for a shipment."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT * FROM pipeline_checkpoints WHERE shipment_id = ?",
            (shipment_id,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["state"] = json.loads(result.pop("state_json"))
        return result
    finally:
        conn.close()


def store_pipeline_result(state: dict[str, Any]):
    """Store complete pipeline result from LangGraph state."""
    conn = get_connection()
    try:
        shipment_id = state["shipment_id"]
        customer_id = state["customer_id"]

        # Clean up any previous data for this shipment (re-processing)
        conn.execute("DELETE FROM validations WHERE shipment_id = ?", (shipment_id,))
        conn.execute("DELETE FROM documents WHERE shipment_id = ?", (shipment_id,))
        conn.execute("DELETE FROM shipments WHERE id = ?", (shipment_id,))

        # Get customer name from rules
        from backend.models.rules import load_customer_rules
        try:
            rules = load_customer_rules(customer_id)
            customer_name = rules.customer_name
        except Exception:
            customer_name = customer_id

        decision_result = state.get("decision_result", {})
        cross_val = state.get("cross_validation_result")

        # Insert shipment
        conn.execute("""
            INSERT OR REPLACE INTO shipments
            (id, customer_id, customer_name, status, decision, decision_reasoning,
             draft_email, overall_confidence, document_count, cross_validation_json,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            shipment_id,
            customer_id,
            customer_name,
            state.get("status", "stored"),
            decision_result.get("decision"),
            decision_result.get("reasoning"),
            decision_result.get("draft_email"),
            decision_result.get("overall_confidence", 0.0),
            len(state.get("extraction_results", [])),
            json.dumps(cross_val) if cross_val else None,
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ))

        # Insert documents and validations
        extraction_results = state.get("extraction_results", [])
        validation_results = state.get("validation_results", [])

        for i, ext in enumerate(extraction_results):
            if "error" in ext:
                continue

            doc_id = ext.get("document_id", str(uuid.uuid4())[:8])

            # Compute avg confidence
            data = ext.get("extracted_data", {})
            confidences = []
            for key, val in data.items():
                if isinstance(val, dict) and "confidence" in val:
                    confidences.append(val["confidence"])
            avg_conf = sum(confidences) / len(confidences) if confidences else 0.0

            conn.execute("""
                INSERT OR REPLACE INTO documents
                (id, shipment_id, document_type, file_path, file_name,
                 extracted_json, raw_ocr_text, extraction_confidence_avg,
                 model_used, tokens_used, processing_time_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_id,
                shipment_id,
                ext.get("document_type", "unknown"),
                state["document_paths"][i] if i < len(state.get("document_paths", [])) else None,
                ext.get("file_name"),
                json.dumps(data),
                ext.get("raw_ocr_text"),
                avg_conf,
                ext.get("model_used"),
                ext.get("tokens_used"),
                ext.get("processing_time_ms"),
                datetime.now(timezone.utc).isoformat(),
            ))

            # Insert validation results for this document
            if i < len(validation_results):
                val_result = validation_results[i]
                if "error" not in val_result:
                    doc_type = ext.get("document_type", "unknown")
                    for fv in val_result.get("field_validations", []):
                        conn.execute("""
                            INSERT INTO validations
                            (id, document_id, shipment_id, document_type, field_name,
                             found_value, expected_value, match_result,
                             match_confidence, extraction_confidence, severity,
                             reasoning, source_snippet, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            str(uuid.uuid4())[:8],
                            doc_id,
                            shipment_id,
                            doc_type,
                            fv.get("field_name"),
                            fv.get("found_value"),
                            fv.get("expected_value"),
                            fv.get("result"),
                            fv.get("match_confidence"),
                            fv.get("extraction_confidence"),
                            fv.get("severity"),
                            fv.get("reasoning"),
                            fv.get("source_snippet"),
                            datetime.now(timezone.utc).isoformat(),
                        ))

        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def get_shipments(
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Query shipments with optional filters."""
    conn = get_connection()
    query = "SELECT * FROM shipments WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if customer_id:
        query += " AND customer_id = ?"
        params.append(customer_id)
    if decision:
        query += " AND decision = ?"
        params.append(decision)

    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_shipment_detail(shipment_id: str) -> Optional[dict]:
    """Get full shipment detail including documents and validations."""
    conn = get_connection()

    shipment = conn.execute(
        "SELECT * FROM shipments WHERE id = ?", (shipment_id,)
    ).fetchone()

    if not shipment:
        conn.close()
        return None

    result = dict(shipment)

    # Get documents
    docs = conn.execute(
        "SELECT * FROM documents WHERE shipment_id = ? ORDER BY document_type",
        (shipment_id,),
    ).fetchall()
    result["documents"] = []
    for doc in docs:
        doc_dict = dict(doc)
        if doc_dict.get("extracted_json"):
            doc_dict["extracted_data"] = json.loads(doc_dict["extracted_json"])
        result["documents"].append(doc_dict)

    # Get validations
    validations = conn.execute(
        "SELECT * FROM validations WHERE shipment_id = ? ORDER BY field_name",
        (shipment_id,),
    ).fetchall()
    result["validations"] = [dict(v) for v in validations]

    # Parse cross-validation
    if result.get("cross_validation_json"):
        result["cross_validation"] = json.loads(result["cross_validation_json"])

    conn.close()
    return result


def update_shipment_status(shipment_id: str, status: str, **kwargs):
    """Update shipment status and optional fields."""
    conn = get_connection()
    sets = ["status = ?", "updated_at = ?"]
    params = [status, datetime.now(timezone.utc).isoformat()]

    for key, value in kwargs.items():
        sets.append(f"{key} = ?")
        params.append(value)

    params.append(shipment_id)
    conn.execute(f"UPDATE shipments SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()
    conn.close()


def execute_query(sql: str) -> list[dict]:
    """Execute a read-only SQL query and return results as dicts."""
    # Safety: only allow SELECT
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    # Check for forbidden SQL statements (as standalone words, not substrings)
    # This avoids false positives like "updated_at" matching "UPDATE"
    import re
    forbidden = ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE"]
    for word in forbidden:
        if re.search(r'\b' + word + r'\b', stripped) and not re.match(r'^SELECT\b', stripped[:10]):
            # Make sure it's an actual SQL statement keyword, not a column/table name
            # Check if the word appears as a standalone statement (not after a dot or underscore)
            pattern = r'(?<![_.\w])' + word + r'(?![_\w])'
            if re.search(pattern, stripped):
                raise ValueError(f"Forbidden SQL keyword: {word}")

    conn = get_connection()
    try:
        rows = conn.execute(sql).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()
