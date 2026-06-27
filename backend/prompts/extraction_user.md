<document_type>{document_type}</document_type>

<task>
Extract all fields listed in the provided schema from the attached document.
</task>

<instructions>
1. Return every key from the schema exactly once.
2. Use `null` for missing or ambiguous values.
3. Set `confidence` as a float between `0.0` and `1.0`.
4. Keep `source_snippet` as an exact excerpt from the document.
5. Keep `page_number` if you can identify it; otherwise use `null`.
6. DO NOT invent values from other shipment documents.
7. DO NOT collapse distinct values into a normalized summary.
</instructions>

<schema>
{field_schema}
</schema>

<formatting_reminder>
- The output MUST be strictly valid JSON.
- DO NOT add any keys that are not present in the schema (except the required quality score keys).
- DO NOT include prose, bullets, or markdown formatting (like ```json). Just output the raw JSON object.
</formatting_reminder>
