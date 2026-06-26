"""Natural Language Query Engine — text-to-SQL using Claude Haiku."""

import json
import logging

import anthropic

from backend.config.settings import settings
from backend.models.database import execute_query

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

SYSTEM_PROMPT = """You are a SQL query generator for a trade document validation system.
The database uses SQLite with these tables:

shipments (id TEXT, customer_id TEXT, customer_name TEXT, status TEXT, decision TEXT,
           decision_reasoning TEXT, draft_email TEXT, overall_confidence REAL,
           document_count INTEGER, created_at TIMESTAMP, updated_at TIMESTAMP)
-- status: incoming, processing, extracted, validated, approved, flagged, amendment_required, stored, error
-- decision: approved, flagged, amendment_required

documents (id TEXT, shipment_id TEXT, document_type TEXT, file_path TEXT, file_name TEXT,
           extracted_json TEXT, extraction_confidence_avg REAL, model_used TEXT,
           tokens_used INTEGER, processing_time_ms INTEGER, created_at TIMESTAMP)
-- document_type: bill_of_lading, commercial_invoice, packing_list, certificate_of_origin

validations (id TEXT, document_id TEXT, shipment_id TEXT, field_name TEXT, found_value TEXT,
             expected_value TEXT, match_result TEXT, match_confidence REAL,
             extraction_confidence REAL, severity TEXT, reasoning TEXT, created_at TIMESTAMP)
-- match_result: match, mismatch, uncertain
-- severity: critical, high, medium, low

Rules:
1. ONLY generate SELECT queries. Never INSERT, UPDATE, DELETE, or DROP.
2. Use proper JOIN syntax when combining tables.
3. For date filtering, use SQLite date functions: date('now'), date('now', '-7 days')
4. Return ONLY a JSON object: {"sql": "SELECT ...", "explanation": "This query..."}
5. Keep queries simple and efficient.

Examples:
User: "How many shipments were flagged this week?"
{"sql": "SELECT COUNT(*) as count FROM shipments WHERE decision = 'flagged' AND created_at >= date('now', '-7 days')", "explanation": "Counts shipments with 'flagged' decision from the last 7 days."}

User: "Show me all critical mismatches"
{"sql": "SELECT v.shipment_id, v.field_name, v.found_value, v.expected_value, v.reasoning, s.customer_name FROM validations v JOIN shipments s ON v.shipment_id = s.id WHERE v.match_result = 'mismatch' AND v.severity = 'critical' ORDER BY v.created_at DESC", "explanation": "Lists all critical severity mismatches with shipment details."}

User: "What's the average confidence score?"
{"sql": "SELECT ROUND(AVG(extraction_confidence_avg), 3) as avg_confidence FROM documents WHERE extraction_confidence_avg > 0", "explanation": "Calculates the average extraction confidence across all documents."}

User: "Show me everything pending review for HomeStyle Germany"
{"sql": "SELECT s.id, s.status, s.decision, s.created_at, v.field_name, v.found_value, v.expected_value, v.match_result, v.severity FROM shipments s LEFT JOIN validations v ON s.id = v.shipment_id WHERE s.customer_name LIKE '%HomeStyle%' AND s.decision = 'flagged' ORDER BY s.created_at DESC", "explanation": "Lists flagged shipments for HomeStyle Germany with validation details."}"""


def query_natural_language(question: str) -> dict:
    """Process a natural language question into SQL, execute, and return results."""
    # Step 1: Generate SQL using Claude Haiku
    try:
        response = client.messages.create(
            model=settings.query_model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": question}],
        )
        raw = response.content[0].text.strip()

        # Parse JSON from response
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        parsed = json.loads(raw)
        sql = parsed.get("sql", "")
        explanation = parsed.get("explanation", "")

    except Exception as e:
        logger.error(f"SQL generation failed: {e}")
        return {
            "question": question,
            "sql": "",
            "explanation": "",
            "results": [],
            "answer": f"Sorry, I couldn't generate a query for that question. Error: {str(e)}",
            "error": str(e),
        }

    # Step 2: Execute SQL
    try:
        results = execute_query(sql)
    except Exception as e:
        logger.error(f"SQL execution failed: {e}")
        return {
            "question": question,
            "sql": sql,
            "explanation": explanation,
            "results": [],
            "answer": f"The query was generated but failed to execute: {str(e)}",
            "error": str(e),
        }

    # Step 3: Generate natural language answer
    answer = _generate_nl_answer(question, results)

    return {
        "question": question,
        "sql": sql,
        "explanation": explanation,
        "results": results[:100],
        "answer": answer,
        "error": None,
    }


def _generate_nl_answer(question: str, results: list[dict]) -> str:
    """Convert query results to a natural language answer."""
    if not results:
        return "No results found for your query."

    if len(results) == 1 and len(results[0]) == 1:
        key = list(results[0].keys())[0]
        value = results[0][key]
        return f"The answer is: {value}"

    try:
        results_str = json.dumps(results[:20], indent=2, default=str)
        response = client.messages.create(
            model=settings.query_model,
            max_tokens=300,
            system="Given a user question and database query results, provide a brief, helpful natural language answer. Only state what the data shows. Be concise.",
            messages=[{
                "role": "user",
                "content": f"Question: {question}\n\nResults ({len(results)} rows):\n{results_str}",
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        logger.warning(f"NL answer generation failed: {e}")
        return f"Found {len(results)} result(s). See the data table below."
