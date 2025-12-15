from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm.openai_client import OpenAIClient
from app.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)


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
    """Structured plan for executing an intent against the SQL backend."""

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
    """LLM-derived routing decision for a user question."""

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
ROUTER_SYSTEM = load_prompt("router_system.txt")


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
    """Routes user questions to query plans or clarification/refusal actions using the LLM."""

    def __init__(self, llm: OpenAIClient):
        self.llm = llm

    def route(self, question: str) -> RouterResult:
        """Run the routing prompt and validate the JSON response."""
        logger.debug("Routing question: %s", question)
        obj = self.llm.json_schema(
            system=ROUTER_SYSTEM,
            user=question,
            schema=ROUTER_RESULT_SCHEMA,
        )
        result = RouterResult.model_validate(obj)
        logger.info(
            "Router decision: action=%s intent=%s",
            result.action,
            getattr(result.plan, "intent", None),
        )
        return result
