# Technical Write-up: GoComet Nova

## 1. System Architecture

The following diagram illustrates the data flow, agent boundaries, and state management within the Nova platform.

![System Architecture](data:image/png;base64,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)

**Key Architectural Decisions:**
*   **State Lives in the Database:** LangGraph’s state is backed by a SQLite checkpointer. This means the graph state is fully serialized and saved at every node transition, ensuring durability.
*   **Sharp Agent Boundaries:** LLMs handle extraction, validation, and drafting. The Validator Agent is a true Tool-Calling Agent that uses Anthropic's parallel tool calling to delegate complex math and string logic to deterministic Python functions, completely eliminating hallucination risk for numeric checks while maintaining the intelligence of an LLM.

---

## 2. The Three Nastiest Failure Modes

During testing and development, I encountered several complex failure modes that standard prompts couldn't handle.

### 1. The "Clean" Shipment False Failure
*   **The Reality:** Our "clean" test shipment (`shipment_1`) was failing validation. The customer rules demanded an `invoice_number`, but the agent couldn't find one on the Bill of Lading (BOL).
*   **The Issue:** BOLs generally *do not have* invoice numbers; they belong on the Commercial Invoice. A naive validator applies all rules to all documents.
*   **The Fix:** Implemented a **Document-Type Awareness Layer**. The Validator now filters rules based on the document type, skipping `required` checks for fields that don't naturally belong on that specific document, preventing false discrepancies.

### 2. Cross-Document Formatting Discrepancies
*   **The Reality:** The Gross Weight on the BOL was listed as `4,250 KG`, but on the Packing List, it was written as `4.250 MT`. 
*   **The Issue:** A simple string equality check or basic LLM comparison fails here. A human knows these are identical, but the machine flags a discrepancy, lowering the Straight-Through Processing (STP) rate.
*   **The Fix:** Built a robust `_extract_numeric` parser in the Validator that intelligently isolates floats and units, normalizes them to a common base (e.g., converting Metric Tons to Kilograms), and applies a customer-defined percentage tolerance (e.g., ±0.5%) before comparing.

### 3. Mid-Pipeline State Loss (The Silent Crash)
*   **The Reality:** If the FastAPI server restarted while a large PDF was being extracted, the pipeline died. The CG operator was left with a shipment perpetually stuck in "Processing".
*   **The Issue:** LangGraph uses an in-memory `MemorySaver` by default. 
*   **The Fix:** Implemented a custom `SQLiteBackedMemorySaver`. Because LangGraph allows custom checkpointers, we intercept the blobs at every node and write them to `nova.db`. If the server crashes, a recovery script can re-instantiate the graph using the `thread_id` and resume exactly from the failed node.

---

## 4. Observability: Tracing a Shipment at Scale

If Nova is running in production for 50 customers processing thousands of documents, simple console logs are useless. Here is how observability is structured:

### Tracing a Single Shipment
1.  **Unique Trace ID:** The moment an email arrives, a unique `shipment_id` and `thread_id` are generated. This ID propagates through Kafka, FastAPI, LangGraph, and the UI.
2.  **LLM Observability (Langfuse / OpenTelemetry):** We wrap every Claude API call in a Langfuse tracer. If a specific extraction fails, we can pull up the trace to see the exact base64 image sent, the prompt, the latency, and the exact token usage for that specific hop.
3.  **State Emissions (SSE):** The backend emits Server-Sent Events (SSE) at every graph node boundary (`extracting`, `validated`, `decided`). The UI subscribes to this stream, allowing operators to see exactly where a shipment is in the pipeline in real-time.

### The Production Dashboard
An FDE or Engineering Manager looking at the Nova dashboard would see:
*   **Straight-Through Processing (STP) Rate:** The golden metric.
*   **Average Confidence Score by Supplier:** Highlights which suppliers send low-quality scans.
*   **Error Rate by Rule:** Shows which validation rules fail most often (indicating a need for supplier retraining or rule loosening).
*   **P95 Pipeline Latency:** To monitor if the vision model is degrading in speed.

---

## 5. Cost Analysis & Control

Using **claude-sonnet-4-6**, the unit economics are highly favorable for large-scale operations.

### Back-of-the-Envelope Cost (Per Document)
*   **claude-sonnet-4-6 Pricing:** ~$3.00 / 1M input tokens | ~$15.00 / 1M output tokens.
*   **Usage:** A standard 2-page PDF (converted to images) consumes roughly 3,000 input tokens and 500 output tokens.
*   **Calculation:** 
    *   Input: (3,000 / 1,000,000) * $3.00 = `$0.009`
    *   Output: (500 / 1,000,000) * $15.00 = `$0.0075`
*   **Total:** **~$0.0165 per document.**
*   A 4-document shipment costs roughly **~$0.066** to process end-to-end.

### Where it Blows Up & How We Control It
1.  **Infinite Agent Loops:** If the LLM repeatedly outputs invalid JSON, LangGraph could loop infinitely, racking up costs.
    *   *Control:* Hard `recursion_limit` set in LangGraph. After 3 failed retries, it throws a `MaxRetriesExceeded` exception and routes to human review.
2.  **Massive PDFs:** A supplier accidentally attaches a 200-page product catalog instead of a 1-page invoice. Sending 200 pages as images to the Vision API will spike costs instantly.
    *   *Control:* Pre-processing checks. If a PDF exceeds 10 pages, it is rejected by the trigger and flagged for manual triage. Furthermore, we compress images to a maximum dimension (e.g., 1024px) before encoding to base64.

---

## 6. Latency Analysis

### Where is the Slowest Hop?
The **Extractor Agent** is the absolute bottleneck. 
*   **Extraction:** Processing 4 heavy PDFs via the Vision API takes **~4-6 seconds** (even when parallelized, due to network I/O and Anthropic rate limits).
*   **Validation:** Hybrid. Pure Python rules (regex, math) take **< 0.05 seconds**, while non-deterministic semantic reasoning takes **~1-2 seconds**.
*   **Routing/Drafting:** LLM decision-making, reasoning generation, and drafting of a short text email. Takes **~2 - 4 seconds** (two sequential LLM calls, with deterministic fallback if the first fails).

### How to Fix It
To shave seconds off the Extractor hop:
1.  **Text-Layer Sniffing:** Before sending images to the Vision model, check if the PDF has a clean, extractable text layer (via PyMuPDF). If it does, we can pass text to the LLM instead of base64 images. Text processes significantly faster and consumes fewer tokens.
2.  **Aggressive Async:** Ensure that the LangChain/Anthropic API calls are utilizing `asyncio.gather` so that all 4 documents in a shipment are extracted concurrently, reducing the latency to the speed of the single slowest document.

---

## 7. What I'd Do Differently With a Week

If I had a full week instead of a DAW assignment, I would elevate this from a robust POC to enterprise-grade infrastructure:

1.  **Migrate to ClickHouse & Postgres:** SQLite is insufficient for concurrent LangGraph pipeline executions. I would use Postgres for operational state and relationships (Customers, Rules, Shipments) and ClickHouse for the analytical storage (observability logs, extracted fields, confidence scores) as defined in the Nova architecture.
2.  **Vector Database (Weaviate) for Rules:** Managing JSON rule files per customer does not scale. I would ingest customer SOPs into Weaviate, allowing the Validator to perform semantic searches to dynamically fetch rules (e.g., finding the specific demurrage clause for a given port).
3.  **Real Event-Driven Trigger (Kafka / Inbox):** I would build a true email ingester (using AWS SES inbound parsing or Microsoft Graph API) that drops an event into a Kafka topic, which natively triggers the LangGraph worker pool.
4.  **OpenFGA Integration:** Implement relationship-based access control (Zanzibar model) so that a CG operator can only view and validate shipments for their assigned tenants.
