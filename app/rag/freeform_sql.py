from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.llm.openai_client import OpenAIClient
from app.rag.sql_safety import enforce_sql_safety


SQL_SYSTEM = """You write MySQL SELECT queries for a small business database.

Schema:
- clients(client_id, client_name, industry, country)
- invoices(invoice_id, client_id, invoice_date, due_date, status, currency, fx_rate_to_usd)
- invoice_line_items(line_id, invoice_id, service_name, quantity, unit_price, tax_rate)

Join rules:
- invoices.client_id = clients.client_id
- invoice_line_items.invoice_id = invoices.invoice_id

Rules (STRICT):
- Output ONLY ONE SQL statement.
- It MUST be a SELECT query.
- Use only the 3 tables above.
- No markdown, no backticks, no explanations.
- Prefer explicit columns (avoid SELECT *).
- If query may return many rows, include LIMIT 50.
- For totals including tax: (quantity * unit_price) * (1 + tax_rate)
"""

REPAIR_SYSTEM = """You fix MySQL SELECT queries.

Rules (STRICT):
- Output ONLY ONE corrected SQL statement.
- It MUST be a SELECT query.
- Use only tables: clients, invoices, invoice_line_items.
- No markdown, no commentary.
"""


@dataclass(frozen=True)
class FreeformSQL:
    raw_sql: str
    safe_sql: str


class FreeformSQLGenerator:
    def __init__(self, llm: OpenAIClient):
        self.llm = llm

    def generate(self, question: str) -> FreeformSQL:
        raw = self.llm.text(SQL_SYSTEM, f"Question: {question}").strip().rstrip(";")
        safe = enforce_sql_safety(raw)
        return FreeformSQL(raw_sql=raw + ";", safe_sql=safe)

    def repair(self, question: str, previous_sql: str, error: str) -> FreeformSQL:
        user = (
            f"Question: {question}\n\n"
            f"Failed SQL:\n{previous_sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return a corrected SQL query."
        )
        raw = self.llm.text(REPAIR_SYSTEM, user).strip().rstrip(";")
        safe = enforce_sql_safety(raw)
        return FreeformSQL(raw_sql=raw + ";", safe_sql=safe)
