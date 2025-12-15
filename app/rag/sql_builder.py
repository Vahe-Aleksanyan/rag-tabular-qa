from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
@dataclass(frozen=True)
class BuiltSQL:
    sql: str
    params: Dict[str, Any]
    """Structured SQL text with bound parameters."""


def _safe_limit(n: Optional[int], default: int = 50, min_v: int = 1, max_v: int = 200) -> int:
    """Clamp a numeric limit to a safe range with a default fallback."""
    if n is None:
        return default
    try:
        v = int(n)
    except Exception:
        return default
    return max(min_v, min(max_v, v))


def build_sql(plan) -> BuiltSQL:
    """Build a parameterized SQL string for the given query plan."""
    intent = plan.intent
    logger.debug("Building SQL for intent=%s", intent)

    # ---------- Clients ----------
    if intent == "LIST_CLIENTS":
        return BuiltSQL(
            sql="""
            SELECT client_id, client_name, industry, country
            FROM clients
            ORDER BY client_name
            """,
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

    # ---------- Invoices ----------
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

    # all invoices for a given client name (IDs, dates, due, status, currency)
    if intent == "CLIENT_INVOICES":
        return BuiltSQL(
            sql="""
            SELECT
              i.invoice_id,
              i.invoice_date,
              i.due_date,
              i.status,
              i.currency
            FROM invoices i
            JOIN clients c ON c.client_id = i.client_id
            WHERE c.client_name = :client_name
            ORDER BY i.invoice_date, i.invoice_id
            """,
            params={"client_name": plan.client_name},
        )

    # invoices for client in a given month/year
    if intent == "INVOICES_BY_CLIENT_AND_MONTH":
        return BuiltSQL(
            sql="""
            SELECT
              i.invoice_id,
              i.invoice_date,
              i.due_date,
              i.status,
              i.currency
            FROM invoices i
            JOIN clients c ON c.client_id = i.client_id
            WHERE c.client_name = :client_name
              AND YEAR(i.invoice_date) = :year
              AND MONTH(i.invoice_date) = :month
            ORDER BY i.invoice_date, i.invoice_id
            """,
            params={
                "client_name": plan.client_name,
                "year": plan.year,
                "month": plan.month,
            },
        )

    # overdue invoices as-of a date (uses status + due_date)
    if intent == "OVERDUE_INVOICES_AS_OF_DATE":
        return BuiltSQL(
            sql="""
            SELECT
              i.invoice_id,
              c.client_name,
              i.invoice_date,
              i.due_date,
              i.status,
              i.currency
            FROM invoices i
            JOIN clients c ON c.client_id = i.client_id
            WHERE i.status = 'Overdue'
              AND i.due_date < :as_of_date
            ORDER BY i.due_date, i.invoice_id
            """,
            params={"as_of_date": plan.as_of_date},
        )

    # ---------- Invoice line items ----------
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

    # count line items per service_name
    if intent == "LINE_ITEM_COUNT_BY_SERVICE":
        return BuiltSQL(
            sql="""
            SELECT
              service_name,
              COUNT(*) AS line_item_count
            FROM invoice_line_items
            GROUP BY service_name
            ORDER BY line_item_count DESC, service_name
            """,
            params={},
        )

    # ---------- Revenue / totals ----------
    # total billed per client in a year (incl tax)
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
            ORDER BY total_billed_including_tax DESC, c.client_name
            """,
            params={"year": plan.year},
        )

    # top client by total billed in year (incl tax)
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

    # top N services by revenue in a year (incl tax)
    if intent == "TOP_SERVICES_BY_REVENUE":
        limit = _safe_limit(getattr(plan, "limit", None), default=3, max_v=50)
        logger.debug("Using limit=%s for TOP_SERVICES_BY_REVENUE", limit)
        return BuiltSQL(
            sql=f"""
            SELECT
              li.service_name,
              SUM((li.quantity * li.unit_price) * (1 + li.tax_rate)) AS total_revenue_including_tax
            FROM invoice_line_items li
            JOIN invoices i ON i.invoice_id = li.invoice_id
            WHERE YEAR(i.invoice_date) = :year
            GROUP BY li.service_name
            ORDER BY total_revenue_including_tax DESC, li.service_name
            LIMIT {limit}
            """,
            params={"year": plan.year},
        )

    # revenue grouped by client country for a year (incl tax)
    if intent == "REVENUE_BY_COUNTRY":
        return BuiltSQL(
            sql="""
            SELECT
              c.country,
              SUM((li.quantity * li.unit_price) * (1 + li.tax_rate)) AS total_billed_including_tax
            FROM clients c
            JOIN invoices i ON i.client_id = c.client_id
            JOIN invoice_line_items li ON li.invoice_id = i.invoice_id
            WHERE YEAR(i.invoice_date) = :year
            GROUP BY c.country
            ORDER BY total_billed_including_tax DESC, c.country
            """,
            params={"year": plan.year},
        )

    # for a service, list clients and how much they paid (incl tax)
    if intent == "SERVICE_CLIENT_TOTALS":
        return BuiltSQL(
            sql="""
            SELECT
              c.client_id,
              c.client_name,
              SUM((li.quantity * li.unit_price) * (1 + li.tax_rate)) AS total_paid_including_tax
            FROM invoice_line_items li
            JOIN invoices i ON i.invoice_id = li.invoice_id
            JOIN clients c ON c.client_id = i.client_id
            WHERE li.service_name = :service_name
              AND YEAR(i.invoice_date) = :year
            GROUP BY c.client_id, c.client_name
            ORDER BY total_paid_including_tax DESC, c.client_name
            """,
            params={"service_name": plan.service_name, "year": plan.year},
        )

    # European clients only, top 3 services by revenue in H2 2024
    # NOTE: "European" is ambiguous; we'll define it by a fixed allowlist of EU/Europe countries in router/README,
    # or store an 'is_europe' mapping later. For now we expect plan.countries to be provided by router.
    if intent == "TOP_SERVICES_EU_H2":
        limit = _safe_limit(getattr(plan, "limit", None), default=3, max_v=50)
        logger.debug("Using limit=%s for TOP_SERVICES_EU_H2", limit)
        # Expect: plan.start_date, plan.end_date, plan.countries (list[str])
        # MySQL doesn't support binding a list directly in IN() with SQLAlchemy text easily; we build placeholders.
        countries = list(getattr(plan, "countries", []) or [])
        if not countries:
            # fallback: if router didn't provide, use a conservative set
            countries = ["UK", "France", "Germany", "Netherlands", "Spain", "Italy"]
        logger.debug("Countries used for TOP_SERVICES_EU_H2: %s", countries)

        placeholders = ", ".join([f":c{i}" for i in range(len(countries))])
        params = {f"c{i}": countries[i] for i in range(len(countries))}
        params.update({"start_date": plan.start_date, "end_date": plan.end_date})

        return BuiltSQL(
            sql=f"""
            SELECT
              li.service_name,
              SUM((li.quantity * li.unit_price) * (1 + li.tax_rate)) AS total_revenue_including_tax
            FROM invoice_line_items li
            JOIN invoices i ON i.invoice_id = li.invoice_id
            JOIN clients c ON c.client_id = i.client_id
            WHERE i.invoice_date >= :start_date
              AND i.invoice_date <= :end_date
              AND c.country IN ({placeholders})
            GROUP BY li.service_name
            ORDER BY total_revenue_including_tax DESC, li.service_name
            LIMIT {limit}
            """,
            params=params,
        )

    logger.error("Unsupported intent encountered: %s", intent)
    raise ValueError(f"Unsupported intent: {intent}")
