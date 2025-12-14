from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm.openai_client import OpenAIClient


# -----------------------------
# Intent + plan
# -----------------------------
Intent = Literal[
    # Clients
    "LIST_CLIENTS",
    "CLIENTS_BY_COUNTRY",

    # Invoices
    "INVOICES_BY_MONTH",
    "INVOICES_BY_STATUS",
    "CLIENT_INVOICES",
    "INVOICES_BY_CLIENT_AND_MONTH",
    "OVERDUE_INVOICES_AS_OF_DATE",

    # Line items
    "INVOICE_LINE_ITEMS",
    "LINE_ITEM_COUNT_BY_SERVICE",

    # Revenue / analytics
    "CLIENT_TOTAL_BILLED_BY_YEAR",
    "TOP_CLIENT_BY_YEAR",
    "TOP_SERVICES_BY_REVENUE",
    "REVENUE_BY_COUNTRY",
    "SERVICE_CLIENT_TOTALS",
    "TOP_SERVICES_EU_H2",

    # Freeform fallback
    "FREEFORM_SQL",
]


class QueryPlan(BaseModel):
    model_config = {"frozen": False}

    intent: Intent

    # common entities
    client_name: Optional[str] = None
    country: Optional[str] = None
    invoice_id: Optional[str] = None
    status: Optional[str] = None

    # time filters
    year: Optional[int] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)

    # dates
    as_of_date: Optional[str] = None  # YYYY-MM-DD
    start_date: Optional[str] = None  # YYYY-MM-DD
    end_date: Optional[str] = None    # YYYY-MM-DD

    # service analytics
    service_name: Optional[str] = None

    # top-k
    limit: Optional[int] = Field(default=None, ge=1, le=50)

    # EU countries list (optional)
    countries: Optional[List[str]] = None

    # debugging
    rationale: Optional[str] = None


# -----------------------------
# Router result (query vs clarify)
# -----------------------------
Action = Literal["QUERY", "CLARIFY", "REFUSE"]


class RouterResult(BaseModel):
    action: Action
    plan: Optional[QueryPlan] = None

    # only for CLARIFY
    clarifying_question: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list)

    # only for REFUSE
    refusal_message: Optional[str] = None

    # debugging
    rationale: Optional[str] = None


# -----------------------------
# Prompt
# -----------------------------
ROUTER_SYSTEM = """You route user questions about a small business database (clients, invoices, invoice_line_items).

You must output a JSON object that matches the provided schema (RouterResult).

You have THREE possible actions:
1) action="QUERY": return a plan for retrieval.
2) action="CLARIFY": if question is ambiguous or missing required entities, ask ONE short clarification question and list missing_fields.
3) action="REFUSE": if the question is NOT about the business tables (clients, invoices, invoice line items), politely refuse and suggest in-domain examples.

Allowed intents (for QUERY.action):
- LIST_CLIENTS
- CLIENTS_BY_COUNTRY
- INVOICES_BY_MONTH
- INVOICES_BY_STATUS
- CLIENT_INVOICES
- INVOICES_BY_CLIENT_AND_MONTH
- OVERDUE_INVOICES_AS_OF_DATE
- INVOICE_LINE_ITEMS
- LINE_ITEM_COUNT_BY_SERVICE
- CLIENT_TOTAL_BILLED_BY_YEAR
- TOP_CLIENT_BY_YEAR
- TOP_SERVICES_BY_REVENUE
- REVENUE_BY_COUNTRY
- SERVICE_CLIENT_TOTALS
- TOP_SERVICES_EU_H2
- FREEFORM_SQL (last resort)

Rules:
- Use FREEFORM_SQL only if none of the other intents fit reasonably.
- Never invent IDs or client names that are not in the question.
- Month names like "March 2024" => month=3 and year=2024.
- If question says "as of 2024-12-31" => as_of_date="2024-12-31".
- If question says "H2 2024" => start_date="2024-07-01", end_date="2024-12-31", year=2024.
- If question says "top 3" set limit=3 (otherwise leave null).
- If European countries are not specified, set countries=null.

For CLARIFY:
- action="CLARIFY"
- plan must be null
- clarifying_question must be a single short question
- missing_fields must list the field names you need (e.g., ["invoice_id"] or ["year","month"])
- Do NOT guess missing values.

For QUERY:
- action="QUERY"
- plan must be non-null
- clarifying_question should be null
- missing_fields should be empty []
- rationale: one sentence.

For REFUSE:
- action="REFUSE"
- plan must be null
- clarifying_question must be null
- missing_fields should be []
- refusal_message must politely explain the scope and give 2-3 example questions in scope.
"""


# -----------------------------
# JSON Schemas
# -----------------------------
QUERY_PLAN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "intent": {"type": "string", "enum": list(Intent.__args__)},  # type: ignore
        "client_name": {"type": ["string", "null"]},
        "country": {"type": ["string", "null"]},
        "invoice_id": {"type": ["string", "null"]},
        "status": {"type": ["string", "null"]},
        "year": {"type": ["integer", "null"]},
        "month": {"type": ["integer", "null"], "minimum": 1, "maximum": 12},
        "as_of_date": {"type": ["string", "null"]},
        "start_date": {"type": ["string", "null"]},
        "end_date": {"type": ["string", "null"]},
        "service_name": {"type": ["string", "null"]},
        "limit": {"type": ["integer", "null"], "minimum": 1, "maximum": 50},
        "countries": {"type": ["array", "null"], "items": {"type": "string"}},
        "rationale": {"type": ["string", "null"]},
    },
    "required": [
        "intent",
        "client_name",
        "country",
        "invoice_id",
        "status",
        "year",
        "month",
        "as_of_date",
        "start_date",
        "end_date",
        "service_name",
        "limit",
        "countries",
        "rationale",
    ],
}

ROUTER_RESULT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "action": {"type": "string", "enum": ["QUERY", "CLARIFY", "REFUSE"]},
        "plan": {"anyOf": [{"type": "null"}, QUERY_PLAN_SCHEMA]},
        "clarifying_question": {"type": ["string", "null"]},
        "missing_fields": {"type": "array", "items": {"type": "string"}},
        "refusal_message": {"type": ["string", "null"]},
        "rationale": {"type": ["string", "null"]},
    },
    "required": ["action", "plan", "clarifying_question", "missing_fields", "refusal_message", "rationale"],
}


# -----------------------------
# Router
# -----------------------------
class Router:
    def __init__(self, llm: OpenAIClient):
        self.llm = llm

    def route(self, question: str) -> RouterResult:
        obj = self.llm.json_schema(
            system=ROUTER_SYSTEM,
            user=question,
            schema=ROUTER_RESULT_SCHEMA,
        )
        return RouterResult.model_validate(obj)
