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

You must output a JSON object that strictly matches the provided schema (RouterResult).
Do not include any text outside the JSON.

You have THREE possible actions:
1) action="QUERY": return a plan for retrieval.
2) action="CLARIFY": if the question is ambiguous or missing required entities, ask ONE short clarification question and list missing_fields.
3) action="REFUSE": if the question is NOT about the business tables (clients, invoices, invoice line items), politely refuse and suggest in-domain examples.

Allowed intents (for action="QUERY"):
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
- FREEFORM_SQL (last resort only)

General rules:
- Choose exactly ONE action.
- Use FREEFORM_SQL only if none of the listed intents fit reasonably.
- Never invent IDs, names, dates, or values not explicitly present.
- If a field is not mentioned, leave it null.
- rationale must be ONE short sentence explaining the decision.

Date extraction rules:
- "March 2024" → month=3, year=2024
- "as of 2024-12-31" → as_of_date="2024-12-31"
- "H2 2024" → start_date="2024-07-01", end_date="2024-12-31", year=2024
- "top 3" → limit=3 (otherwise leave null)

IMPORTANT DISAMBIGUATION (Overdue invoices):
- If the question asks for invoices with status "Overdue" (e.g. "marked as overdue", "currently overdue"), use INVOICES_BY_STATUS with status="Overdue".
- Use OVERDUE_INVOICES_AS_OF_DATE ONLY when an explicit cutoff date is mentioned (e.g. "as of 2024-12-31").
- The word "currently" alone does NOT imply an as-of date.

For CLARIFY:
- action="CLARIFY"
- plan must be null
- clarifying_question must be ONE short question
- missing_fields must list required fields (e.g., ["year"], ["invoice_id"])
- Do NOT guess or infer missing values

For QUERY:
- action="QUERY"
- plan must be non-null
- clarifying_question must be null
- missing_fields must be []
- rationale must be present

For REFUSE:
- action="REFUSE"
- plan must be null
- clarifying_question must be null
- missing_fields must be []
- refusal_message must politely explain the scope AND give 2–3 valid example questions

Examples:

User: "Which invoices are currently marked as Overdue?"
→ action="QUERY", intent="INVOICES_BY_STATUS", status="Overdue"

User: "Which invoices are overdue as of 2024-12-31?"
→ action="QUERY", intent="OVERDUE_INVOICES_AS_OF_DATE", as_of_date="2024-12-31"

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
