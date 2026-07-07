# Sample Queries — Natural Language Query Layer

These are real natural-language questions run against the live system on **2026-07-07**, via `POST /api/query` (also available from the **Knowledge Base** tab in the UI). Each one shows: the question asked, the SQL Claude generated against the live `nova.db` schema, the row count actually returned, and the natural-language answer produced from those real rows.

The pipeline for every query is: **question → LLM generates read-only SQL → SQL executes against SQLite → results are summarized back in plain English.** Nothing here is hand-scripted; the SQL and the numbers below are exactly what the running system produced.

---

## 1. Aggregate count — "How many shipments were flagged this week?"

**Generated SQL:**
```sql
SELECT COUNT(*) AS count FROM shipments
WHERE decision = 'flagged' AND created_at >= date('now', '-7 days')
```

**Result:** 1 row → `count = 1`
**Answer:** *"The answer is: 1"*

---

## 2. Cross-table join with a filter that matched — "Show me all high severity mismatches"

**Generated SQL:**
```sql
SELECT v.shipment_id, v.field_name, v.found_value, v.expected_value, v.match_result,
       v.severity, v.reasoning, v.match_confidence, s.customer_name, s.status, s.decision
FROM validations v
JOIN shipments s ON v.shipment_id = s.id
WHERE v.severity = 'high' AND v.match_result = 'mismatch'
ORDER BY v.created_at DESC
```

**Result:** 17 rows across 6 shipments. Sample row:
```json
{
  "shipment_id": "SHP-D7CC739B",
  "field_name": "hs_code",
  "found_value": null,
  "expected_value": "Format: ####.##.##",
  "match_result": "mismatch",
  "severity": "high",
  "reasoning": "Required field 'hs_code' is empty.",
  "match_confidence": 1.0,
  "customer_name": "BritFashion Retail Group Plc",
  "status": "stored",
  "decision": "amendment_required"
}
```
**Answer:** *"There are 17 high severity mismatches across 6 shipments, all involving missing required fields. BritFashion Retail Group Plc (5 shipments): SHP-D7CC739B, SHP-7C09A7C7, SHP-7E951A6F, SHP-914C0E30, SHP-D2ABFD75 — Issue: Missing `hs_code`..."*

---

## 3. A filter that correctly matched **zero** rows — "Show me all critical mismatches"

**Generated SQL:**
```sql
SELECT v.shipment_id, v.field_name, v.found_value, v.expected_value, v.reasoning, s.customer_name
FROM validations v
JOIN shipments s ON v.shipment_id = s.id
WHERE v.match_result = 'mismatch' AND v.severity = 'critical'
ORDER BY v.created_at DESC
```

**Result:** 0 rows.
**Answer:** *"No results found for your query."*

Included deliberately: the current dataset's field-level `validations.severity` column only ever stores `high` (the word "critical" appears in the Router's free-text `decision_reasoning`, e.g. "CRITICAL CROSS-DOCUMENT DISCREPANCIES", but that's a different, less structured signal than per-field severity). This confirms the query layer does the honest thing on a genuine miss — it says "no results," it does not hallucinate rows to look useful.

---

## 4. Part 2 — customer-scoped pending review (the exact assignment example) — "Show me everything pending review for BritFashion Retail"

**Generated SQL:**
```sql
SELECT id, decision, decision_reasoning, overall_confidence, source, sender_email, subject, created_at
FROM shipments
WHERE customer_name LIKE '%BritFashion Retail%'
  AND decision IN ('flagged', 'amendment_required')
  AND status NOT IN ('approved', 'amendment_sent')
ORDER BY created_at DESC
```

**Result:** 4 rows — `SHP-7C09A7C7`, `SHP-7E951A6F`, `SHP-914C0E30`, `SHP-D2ABFD75`, all `amendment_required` / `stored` (i.e. drafted but not yet sent by CG).

**Negative control:** the same question for **American Home Furnishings** — after manually approving that customer's one shipment via `PUT /api/shipments/{id}/approve` — correctly returned **0 rows**, confirming the `status NOT IN ('approved', 'amendment_sent')` filter excludes resolved shipments rather than just filtering on decision alone.

**Rephrased version** (not the example wording, to test generalization) — "What shipments are still awaiting CG action for BritFashion?" — produced the same filtering logic (`decision IN (...) AND status NOT IN (...)`) and the same 4 rows, confirming the model isn't just pattern-matching the PRD's example sentence.

---

## 5. Part 2 — inbox-specific aggregate — "How many emails came in from the SU inbox today and how many are still pending?"

**Generated SQL:**
```sql
SELECT COUNT(*) AS total_today,
       SUM(CASE WHEN decision IN ('flagged','amendment_required')
                 AND status NOT IN ('approved','amendment_sent')
                THEN 1 ELSE 0 END) AS pending
FROM shipments
WHERE source = 'email' AND date(received_at) = date('now')
```

**Result:** 1 row → `total_today = 6`, `pending = 5`
**Answer:** *"Based on today's data: 6 emails came in from the SU (Shipping Unit) inbox, 5 of those are still pending review."*

This is the query that proves the "hand-off" step in Part 2 — Step 5, "Verified output is stored and queryable via your Part 1 query layer" — actually works: email-triggered shipments (`source = 'email'`) are indistinguishable from manually-uploaded ones as far as storage goes, but fully filterable by source, customer, decision, and status.

---

## How to reproduce

```bash
curl -s -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me everything pending review for BritFashion Retail"}' | python3 -m json.tool
```

Or from the UI: open the **Knowledge Base** tab and type any of the questions above.
