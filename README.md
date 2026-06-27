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

## 📦 Sample Documents & Scenarios

The repository includes 14 pre-built shipment scenarios located in `data/sample_docs/` to test various edge cases, failure modes, and document types:

- **Shipments 1-3:** Clean, deliberate single errors, and cross-document mismatches.
- **Shipment 4:** Degraded scan quality (Tests OCR fallback and LLM confidence scoring).
- **Shipments 5-8:** Edge cases covering HS Code mismatches, invalid Incoterms, and missing required documents.
- **Shipments 9 & 12:** Low-quality fax scans.
- **Shipments 13-14:** Severely blurry documents specifically designed to trigger the "Low Confidence" auto-flagging pipeline.

### How to Demo
1. Open the UI at `http://localhost:5173`.
2. Navigate to the **Shipments** tab to see real-time extraction and validation states across the sample data.
3. Click into a specific shipment to view the field-by-field validation, confidence scores, and visual discrepancy highlights.
4. Review the AI's drafted amendment email (generated only if discrepancies exist based on the deterministic validation rules).
5. Use the **Natural Language Query** tab to ask contextual questions over the SQLite database (e.g., *"How many shipments were flagged for HS code mismatches today?"*).
