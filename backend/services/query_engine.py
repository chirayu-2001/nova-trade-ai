"""Natural Language Query Engine — text-to-SQL using Claude 3.5 Sonnet."""

import json
import logging
import os

from litellm import completion

from backend.config.settings import settings
from backend.models.database import execute_query
from backend.prompts.loader import load_prompt

logger = logging.getLogger(__name__)

# Ensure API keys are set in environment for litellm
if settings.anthropic_api_key:
    os.environ["ANTHROPIC_API_KEY"] = settings.anthropic_api_key
if settings.openai_api_key:
    os.environ["OPENAI_API_KEY"] = settings.openai_api_key
SYSTEM_PROMPT = load_prompt("query_sql.md")
QUERY_NL_PROMPT = load_prompt("query_nl_answer.md")


def query_natural_language(question: str) -> dict:
    """Process a natural language question into SQL, execute, and return results."""
    # Step 1: Generate SQL using Claude 3.5 Sonnet
    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]
        response = completion(
            model=settings.query_model,
            max_tokens=500,
            temperature=settings.query_temperature,
            messages=messages,
        )
        raw = response.choices[0].message.content.strip()

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
        messages = [
            {"role": "system", "content": QUERY_NL_PROMPT},
            {"role": "user", "content": f"Question: {question}\n\nResults ({len(results)} rows):\n{results_str}"}
        ]
        response = completion(
            model=settings.query_model,
            max_tokens=300,
            temperature=settings.query_temperature,
            messages=messages,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.warning(f"NL answer generation failed: {e}")
        return f"Found {len(results)} result(s). See the data table below."
