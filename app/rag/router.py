from __future__ import annotations

from typing import Any, Dict, Literal, Optional
from pydantic import BaseModel, Field

from app.llm.openai_client import OpenAIClient

# A tight intent set = fewer mistakes, easier SQL mapping
Intent = Literal[
    "LIST_CLIENTS",
    "CLIENTS_BY_COUNTRY",
    "INVOICES_BY_MONTH",
    "INVOICES_BY_STATUS",
    "INVOICE_LINE_ITEMS",
    "CLIENT_INVOICES",
    "CLIENT_TOTAL_BILLED_BY_YEAR",
    "TOP_CLIENT_BY_YEAR",
]

class QueryPlan(BaseModel):
    intent: Intent
    client_name: Optional[str] = None
    country: Optional[str] = None
    year: Optional[int] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)
    status: Optional[str] = None
    invoice_id: Optional[str] = None

    # optional explanation for debugging (still structured)
    rationale: Optional[str] = None


ROUTER_SYSTEM = """You route user questions about a small business database to a structured QueryPlan.
Rules:
- Choose the single best intent from the allowed intents.
- Extract entities exactly (client_name, invoice_id, country, year, month, status).
- If month is mentioned like "March 2024", set month=3 and year=2024.
- If only a year is mentioned, set year and leave month null.
- Never invent IDs or client names that are not in the question.
- If unclear, choose the closest intent and leave fields null rather than guessing.
"""

# JSON Schema for Structured Outputs (strict)
QUERY_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": list(Intent.__args__)},  # type: ignore
        "client_name": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "year": {"type": ["integer", "null"]},
        "month": {"type": ["integer", "null"], "minimum": 1, "maximum": 12},
        "status": {"type": ["string", "null"]},
        "invoice_id": {"type": ["string", "null"]},
        "rationale": {"type": ["string", "null"]},
    },
    "required": ["intent", "client_name", "country", "year", "month", "status", "invoice_id", "rationale"],
}


class Router:
    def __init__(self, llm: OpenAIClient):
        self.llm = llm

    def plan(self, question: str) -> QueryPlan:
        obj = self.llm.json_schema(
            system=ROUTER_SYSTEM,
            user=question,
            schema=QUERY_PLAN_SCHEMA,
        )
        return QueryPlan.model_validate(obj)
