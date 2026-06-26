"""FastAPI application — REST API + SSE for the Nova Trade Document AI system."""

import asyncio
import json
import logging
import os
import shutil
import uuid
from typing import Optional

from fastapi import BackgroundTasks, FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.config.settings import settings
from backend.models.database import (
    get_shipment_detail,
    get_shipments,
    init_database,
    update_shipment_status,
)
from backend.models.rules import list_available_customers, load_customer_rules
from backend.pipeline.graph import run_pipeline
from backend.services.pdf_processor import detect_document_type
from backend.services.query_engine import query_natural_language

logging.basicConfig(level=getattr(logging, settings.log_level))
logger = logging.getLogger(__name__)

app = FastAPI(
    title="GoComet Nova - Trade Document AI",
    version="1.0.0",
    description="Multi-agent AI system for trade document validation",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory status tracking for SSE
pipeline_status: dict[str, dict] = {}


@app.on_event("startup")
async def startup():
    init_database()
    os.makedirs(os.path.join("data", "uploads"), exist_ok=True)
    logger.info("Nova Trade Document AI started")


# --- Pipeline Endpoints ---

class UploadResponse(BaseModel):
    shipment_id: str
    status: str
    message: str


def _run_pipeline_background(
    shipment_id: str,
    file_paths: list[str],
    customer_id: str,
):
    """Run pipeline in background thread and update status."""
    try:
        pipeline_status[shipment_id] = {"status": "extracting", "progress": 0.2}

        result = run_pipeline(
            document_paths=file_paths,
            customer_id=customer_id,
            shipment_id=shipment_id,
        )

        pipeline_status[shipment_id] = {
            "status": result.get("status", "stored"),
            "progress": 1.0,
            "decision": result.get("decision_result", {}).get("decision"),
        }
    except Exception as e:
        logger.error(f"Pipeline failed for {shipment_id}: {e}")
        pipeline_status[shipment_id] = {
            "status": "error",
            "progress": 1.0,
            "error": str(e),
        }


@app.post("/api/upload", response_model=UploadResponse)
async def upload_document(
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
    customer_id: str = Form(default="homestyle_germany"),
):
    """Upload one or more PDF documents and trigger the pipeline."""
    shipment_id = f"SHP-{uuid.uuid4().hex[:8].upper()}"
    saved_paths = []

    upload_dir = os.path.join("data", "uploads", shipment_id)
    os.makedirs(upload_dir, exist_ok=True)

    for file in files:
        file_path = os.path.join(upload_dir, file.filename)
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)
        saved_paths.append(file_path)

    pipeline_status[shipment_id] = {"status": "incoming", "progress": 0.0}

    background_tasks.add_task(
        _run_pipeline_background, shipment_id, saved_paths, customer_id
    )

    return UploadResponse(
        shipment_id=shipment_id,
        status="processing",
        message=f"Pipeline started for {len(saved_paths)} document(s)",
    )


@app.post("/api/process-sample")
async def process_sample(
    background_tasks: BackgroundTasks,
    shipment_folder: str = Form(...),
    customer_id: str = Form(default="homestyle_germany"),
):
    """Process a sample shipment from the data/sample_docs directory."""
    sample_dir = os.path.join(settings.sample_docs_dir, shipment_folder)
    if not os.path.exists(sample_dir):
        return JSONResponse(
            status_code=404,
            content={"error": f"Sample folder not found: {shipment_folder}"},
        )

    # Find all PDFs in the folder (exclude degraded versions by default)
    pdf_files = sorted([
        os.path.join(sample_dir, f)
        for f in os.listdir(sample_dir)
        if f.endswith(".pdf") and "degraded" not in f
    ])

    if not pdf_files:
        return JSONResponse(
            status_code=404,
            content={"error": "No PDF files found in sample folder"},
        )

    # Load metadata for shipment ID
    metadata_path = os.path.join(settings.sample_docs_dir, "shipment_metadata.json")
    shipment_id = None
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            metadata = json.load(f)
        if shipment_folder in metadata:
            shipment_id = metadata[shipment_folder].get("id")

    if not shipment_id:
        shipment_id = f"SHP-{uuid.uuid4().hex[:8].upper()}"

    pipeline_status[shipment_id] = {"status": "incoming", "progress": 0.0}

    background_tasks.add_task(
        _run_pipeline_background, shipment_id, pdf_files, customer_id
    )

    return {
        "shipment_id": shipment_id,
        "status": "processing",
        "documents": [os.path.basename(p) for p in pdf_files],
        "customer_id": customer_id,
    }


# --- Status SSE ---

@app.get("/api/pipeline/{shipment_id}/status")
async def pipeline_sse(shipment_id: str):
    """Server-Sent Events endpoint for real-time pipeline status."""
    async def event_generator():
        last_status = None
        timeout = 120  # 2 minutes max
        elapsed = 0
        while elapsed < timeout:
            status = pipeline_status.get(shipment_id, {"status": "unknown"})
            if status != last_status:
                yield {"data": json.dumps(status)}
                last_status = status.copy()
                if status.get("status") in ("stored", "error", "decided"):
                    break
            await asyncio.sleep(0.5)
            elapsed += 0.5
        yield {"data": json.dumps({"status": "timeout"})}

    return EventSourceResponse(event_generator())


# --- Shipment Endpoints ---

@app.get("/api/shipments")
async def list_shipments(
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
    decision: Optional[str] = None,
    limit: int = 50,
):
    """List shipments with optional filters."""
    return get_shipments(status=status, customer_id=customer_id, decision=decision, limit=limit)


@app.get("/api/shipments/{shipment_id}")
async def shipment_detail(shipment_id: str):
    """Get full shipment detail with extraction, validation, and decision."""
    result = get_shipment_detail(shipment_id)
    if not result:
        return JSONResponse(status_code=404, content={"error": "Shipment not found"})
    return result


@app.put("/api/shipments/{shipment_id}/approve")
async def approve_shipment(shipment_id: str):
    """CG approves a shipment."""
    update_shipment_status(shipment_id, "approved")
    return {"shipment_id": shipment_id, "status": "approved"}


class AmendmentRequest(BaseModel):
    edited_email: str


@app.put("/api/shipments/{shipment_id}/send-amendment")
async def send_amendment(shipment_id: str, body: AmendmentRequest):
    """CG sends an edited amendment email."""
    update_shipment_status(
        shipment_id, "amendment_sent", draft_email=body.edited_email
    )
    return {"shipment_id": shipment_id, "status": "amendment_sent"}


# --- Query Endpoint ---

class QueryRequest(BaseModel):
    question: str


@app.post("/api/query")
async def natural_language_query(body: QueryRequest):
    """Process a natural language query over stored shipment data."""
    return query_natural_language(body.question)


# --- Utility Endpoints ---

@app.get("/api/customers")
async def list_customers():
    """List available customer rule sets."""
    customers = list_available_customers()
    result = []
    for cid in customers:
        try:
            rules = load_customer_rules(cid)
            result.append({
                "customer_id": cid,
                "customer_name": rules.customer_name,
                "rule_count": len(rules.rules),
            })
        except Exception:
            result.append({"customer_id": cid, "customer_name": cid, "rule_count": 0})
    return result


@app.get("/api/sample-shipments")
async def list_sample_shipments():
    """List available sample shipments."""
    metadata_path = os.path.join(settings.sample_docs_dir, "shipment_metadata.json")
    if not os.path.exists(metadata_path):
        return []
    with open(metadata_path) as f:
        return json.load(f)


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Nova Trade Document AI"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
