# GoComet Nova — Trade Document AI Validation System

Nova is an AI-native logistics platform built for the GoComet Full-Stack AI Engineer Day Assignment. It acts as an orchestration layer to autonomously validate inbound trade documents (Bills of Lading, Commercial Invoices, Packing Lists), cross-reference them against customer rules (using a combination of deterministic and non-deterministic methods), flag discrepancies, and draft supplier amendment requests.

## 🚀 Quick Start & Setup Instructions

### Prerequisites
- Python 3.10+
- Node.js 18+
- Anthropic API Key (Claude 3.5 Sonnet)

### 1. Backend Setup

```bash
# Navigate to the project directory
cd gocomet-nova

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install backend dependencies
pip install -r backend/requirements.txt

# Configure Environment Variables
# Create a .env file in the project root
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```
*(Ensure you replace `sk-ant-...` with your actual Anthropic API Key).*

### 2. Frontend Setup

```bash
cd frontend
npm install
```

### 3. Running the Application

You will need two terminal windows to run the full stack locally.

**Terminal 1: FastAPI Backend**
```bash
# From the project root, ensure your virtualenv is activated
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000
```
*The backend runs on `http://localhost:8000` and uses SQLite for state persistence.*

**Terminal 2: React Frontend**
```bash
# From the frontend directory
cd frontend
npm run dev
```

**Open [http://localhost:5173](http://localhost:5173) in your browser to view the application.**

---

## 🧠 Architecture Overview

The system utilizes a Multi-Agent architecture orchestrated via **LangGraph** to ensure deterministic validation while leveraging Claude 3.5 Sonnet for vision extraction and routing.

```
Trigger / PDF Upload 
  ↳ Extractor Agent (Claude 3.5 Sonnet + PyMuPDF) 
      ↳ Validator Agent (Hybrid: Deterministic Math + Non-Deterministic Semantic AI)
          ↳ Cross-Validator Node 
              ↳ Router Agent (Decision & Email Draft) 
                  ↳ SQLite Storage 
                      ↳ Natural Language Query Engine
```

For a comprehensive explanation of the architecture, product choices, and failure handling, please refer to the documentation:
- [Product Requirements Document (PRD)](docs/PRD.md)
- [Technical Write-up](docs/Technical_Writeup.md)

---

## 📬 Part 2 — CG Inbox Workflow

Part 2 wires the same three agents into a simulated Cargo Group (CG) email workflow: instead of a human clicking Upload, a background watcher on `data/inbox/` detects a new "SU email" folder (metadata + PDF attachments) and triggers the pipeline automatically. See [PRD — Part 2](docs/PRD_Part2.md) for the product framing.

```
data/inbox/<slug>/           <- watched folder — drop one of these to simulate a new SU email
    email.json                  {"from", "subject", "customer_id", "body"?}
    *.pdf                       one or more trade document attachments
```

The watcher starts automatically with the backend (`uvicorn backend.main:app`) — no separate process to run. Processed folders are archived under `data/inbox/_processed/` (or `_error/` on failure) so they never re-trigger.

### Try it

1. Start the backend and frontend as described above.
2. Open the **CG Inbox** tab (now the default tab) at `http://localhost:5173`.
3. Click **Simulate Incoming Email** — this copies one of three canned SU emails from `data/inbox_seed/` into `data/inbox/`, exactly as if a supplier had just sent it:
   - `su_clean_shipment` — expect a clean auto-approve draft.
   - `su_mismatch_shipment` — HS code, Incoterm, and weight mismatches across BOL/Invoice/Packing List/CoO → expect an amendment draft listing every discrepancy.
   - `su_messy_scan_shipment` — degraded fax-quality scans → expect low-confidence fields flagged for review, never silently approved.
4. Watch the message move from **New → Processing → Ready for Review** in the mailbox list (polled every 2s).
5. Click the message to see the four Part 2 states in one reading pane: **Verification result** (field-by-field + cross-document consistency), **Discrepancy detail** (click any flagged field), and **Draft reply** at the bottom.
6. Edit the draft if needed and click **Send Amendment to Supplier** / **Confirm Approval** — nothing is ever sent by the agent itself; the pipeline only drafts.

You can also drop your own folder directly into `data/inbox/` following the structure above — the watcher picks it up the same way within ~1.5 seconds.

To ask about pending work across the whole inbox, use the **Knowledge Base** tab, e.g. *"show me everything pending review for BritFashion Retail"* or *"how many emails came in today and how many are still pending?"* — see [`docs/SAMPLE_QUERIES.md`](docs/SAMPLE_QUERIES.md) for real, reproducible examples with the generated SQL and actual results.

---

## 📦 Sample Documents & Scenarios

The repository includes 14 pre-built shipment scenarios located in `data/sample_docs/` to test various edge cases, failure modes, and document types (used directly by the **Document Validation** tab, and reused to build the Part 2 `data/inbox_seed/` emails above):

- **Shipments 1-3:** Clean, deliberate single errors, and cross-document mismatches.
- **Shipment 4:** Degraded scan quality (Tests OCR fallback and LLM confidence scoring).
- **Shipments 5-8:** Edge cases covering HS Code mismatches, invalid Incoterms, and missing required documents.
- **Shipments 9 & 12:** Low-quality fax scans.
- **Shipments 13-14:** Severely blurry documents specifically designed to trigger the "Low Confidence" auto-flagging pipeline.

### How to Demo (Part 1 — manual upload flow)
1. Open the UI at `http://localhost:5173` and go to the **Document Validation** tab.
2. Upload your own PDFs, or click a sample shipment card to run the pipeline on pre-built test data.
3. Watch the pipeline stepper (Extract → Validate → Cross-Check → Decide → Store), then review the field-by-field validation, confidence scores, and discrepancy highlights.
4. Expand **Consolidated Results & Actions** to review the AI's drafted amendment/approval email and reasoning.
5. Use the **Knowledge Base** tab to ask natural-language questions over the SQLite database (e.g., *"How many shipments were flagged for HS code mismatches today?"*), and the **Shipment Audit** tab to browse everything processed so far.

For the Part 2 email-triggered flow, see **CG Inbox Workflow** above.
