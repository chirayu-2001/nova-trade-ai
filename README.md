# GoComet Nova — Trade Document AI Validation System

Multi-agent AI system for automated trade document validation using LangGraph, Claude, and React.

## Quick Start

### 1. Add your Anthropic API key

```bash
# Edit .env and add your key
nano .env
# Set: ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Start the backend

```bash
source .venv/bin/activate
# From the project root:
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000
```

### 3. Start the frontend

```bash
cd frontend
npm run dev
```

Open http://localhost:5173

## Architecture

```
PDF Upload → Extractor Agent (Claude 3.5 Sonnet) → Validator Agent (Rules + Claude) → Router Agent (Decision + Email Draft) → SQLite Storage → NL Query (Claude)
```

## Sample Shipments

6 pre-built shipment scenarios in `data/sample_docs/`:
- Shipment 1: Clean, all correct (India → US, Textiles)
- Shipment 2: 4 deliberate errors (India → Germany, Furniture)
- Shipment 3: Cross-document mismatches (China → India, Electronics)
- Shipment 4: Degraded scan quality (India → UAE, Spices)
- Shipment 5: HS code + Incoterm errors (Bangladesh → UK, Garments)
- Shipment 6: Partial data + abbreviations (India → Japan, Auto Parts)
