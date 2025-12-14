from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Tuple

from sqlalchemy.sql import text

@dataclass(frozen=True)
class BuiltSQL:
    sql: str
    params: Dict[str, Any]


def build_sql(plan) -> BuiltSQL:
    intent = plan.intent

    if intent == "LIST_CLIENTS":
        return BuiltSQL(
            sql="SELECT client_id, client_name, industry, country FROM clients ORDER BY client_name",
            params={},
        )

    if intent == "CLIENTS_BY_COUNTRY":
        return BuiltSQL(
            sql="""
            SELECT client_id, client_name, industry, country
            FROM clients
            WHERE country = :country
            ORDER BY client_name
            """,
            params={"country": plan.country},
        )

    if intent == "INVOICES_BY_MONTH":
        return BuiltSQL(
            sql="""
            SELECT invoice_id, client_id, invoice_date, due_date, status, currency
            FROM invoices
            WHERE YEAR(invoice_date)=:year AND MONTH(invoice_date)=:month
            ORDER BY invoice_date, invoice_id
            """,
            params={"year": plan.year, "month": plan.month},
        )

    if intent == "INVOICES_BY_STATUS":
        return BuiltSQL(
            sql="""
            SELECT invoice_id, client_id, invoice_date, due_date, status, currency
            FROM invoices
            WHERE status = :status
            ORDER BY due_date, invoice_id
            """,
            params={"status": plan.status},
        )

    if intent == "CLIENT_INVOICES":
        return BuiltSQL(
            sql="""
            SELECT i.invoice_id, i.invoice_date, i.due_date, i.status, i.currency
            FROM invoices i
            JOIN clients c ON c.client_id = i.client_id
            WHERE c.client_name = :client_name
            ORDER BY i.invoice_date, i.invoice_id
            """,
            params={"client_name": plan.client_name},
        )

    if intent == "INVOICE_LINE_ITEMS":
        return BuiltSQL(
            sql="""
            SELECT
              line_id,
              invoice_id,
              service_name,
              quantity,
              unit_price,
              tax_rate,
              (quantity * unit_price) * (1 + tax_rate) AS line_total_including_tax
            FROM invoice_line_items
            WHERE invoice_id = :invoice_id
            ORDER BY line_id
            """,
            params={"invoice_id": plan.invoice_id},
        )

    if intent == "CLIENT_TOTAL_BILLED_BY_YEAR":
        return BuiltSQL(
            sql="""
            SELECT
              c.client_id,
              c.client_name,
              SUM((li.quantity * li.unit_price) * (1 + li.tax_rate)) AS total_billed_including_tax
            FROM clients c
            JOIN invoices i ON i.client_id = c.client_id
            JOIN invoice_line_items li ON li.invoice_id = i.invoice_id
            WHERE YEAR(i.invoice_date) = :year
            GROUP BY c.client_id, c.client_name
            ORDER BY total_billed_including_tax DESC
            """,
            params={"year": plan.year},
        )

    if intent == "TOP_CLIENT_BY_YEAR":
        return BuiltSQL(
            sql="""
            SELECT
              c.client_id,
              c.client_name,
              SUM((li.quantity * li.unit_price) * (1 + li.tax_rate)) AS total_billed_including_tax
            FROM clients c
            JOIN invoices i ON i.client_id = c.client_id
            JOIN invoice_line_items li ON li.invoice_id = i.invoice_id
            WHERE YEAR(i.invoice_date) = :year
            GROUP BY c.client_id, c.client_name
            ORDER BY total_billed_including_tax DESC
            LIMIT 1
            """,
            params={"year": plan.year},
        )

    raise ValueError(f"Unsupported intent: {intent}")
