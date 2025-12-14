from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field

from app.llm.openai_client import OpenAIClient


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

    "FREEFORM_SQL"
]


class QueryPlan(BaseModel):
    intent: Intent

    # common entities
    client_name: Optional[str] = None
    country: Optional[str] = None
    invoice_id: Optional[str] = None
    status: Optional[str] = None

    # time filters
    year: Optional[int] = None
    month: Optional[int] = Field(default=None, ge=1, le=12)

    # as-of / date range filters (strings are easiest with mysql + params)
    as_of_date: Optional[str] = None          # YYYY-MM-DD
    start_date: Optional[str] = None          # YYYY-MM-DD
    end_date: Optional[str] = None            # YYYY-MM-DD

    # service analytics
    service_name: Optional[str] = None

    # top-k queries
    limit: Optional[int] = Field(default=None, ge=1, le=50)

    # for EU/Europe filter (router can supply a list of countries)
    countries: Optional[List[str]] = None

    # debugging
    rationale: Optional[str] = None


ROUTER_SYSTEM = """You route user questions about a small business database to a structured QueryPlan.
If the question cannot be answered by the listed intents, choose FREEFORM_SQL.
Allowed intents:
- LIST_CLIENTS: list clients (often with industry/country)
- CLIENTS_BY_COUNTRY: clients filtered by a country (e.g. UK)
- INVOICES_BY_MONTH: invoices in a given month+year (e.g. March 2024)
- INVOICES_BY_STATUS: invoices filtered by status (e.g. Overdue)
- CLIENT_INVOICES: all invoices for a given client_name
- INVOICES_BY_CLIENT_AND_MONTH: invoices for a client in a given month+year
- OVERDUE_INVOICES_AS_OF_DATE: overdue invoices as of a specific date (e.g. 2024-12-31)
- INVOICE_LINE_ITEMS: line items for a given invoice_id, including totals with tax
- LINE_ITEM_COUNT_BY_SERVICE: count of line items per service_name
- CLIENT_TOTAL_BILLED_BY_YEAR: total billed per client in a year (including tax)
- TOP_CLIENT_BY_YEAR: client with the highest total billed in a year
- TOP_SERVICES_BY_REVENUE: top services by revenue in a year (including tax)
- REVENUE_BY_COUNTRY: total billed grouped by client country for a year (including tax)
- SERVICE_CLIENT_TOTALS: for a service_name and year, list clients and totals paid (including tax)
- TOP_SERVICES_EU_H2: European clients only, top services by revenue in H2 2024 (2024-07-01 to 2024-12-31)

Extraction rules:
- Always choose exactly one intent.
- Extract entities exactly as written in the user's question. Do not invent IDs or names.
- Month names like "March 2024" => month=3, year=2024.
- If question mentions "as of 2024-12-31" => as_of_date="2024-12-31".
- If question mentions "H2 2024" => start_date="2024-07-01", end_date="2024-12-31", year=2024.
- If question says "top 3" set limit=3 (otherwise leave null).
- For European clients: if specific European countries are not given, set countries=null (the SQL layer may apply a default list).
- If a field is not explicitly present, leave it null.
- rationale: short reason for the chosen intent (1 sentence).
"""

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
        "countries": {
            "type": ["array", "null"],
            "items": {"type": "string"},
        },

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
