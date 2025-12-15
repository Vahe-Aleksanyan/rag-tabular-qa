from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, Optional

import sqlglot
from sqlglot import exp
import logging

logger = logging.getLogger(__name__)


WRITE_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SQLSafetyConfig:
    """Configuration for SQL safety enforcement."""

    allowed_tables: tuple[str, ...] = ("clients", "invoices", "invoice_line_items")
    require_limit_for_non_aggregate: bool = True
    default_limit: int = 50


class SQLSafetyError(ValueError):
    pass


def is_write_query(sql: str) -> bool:
    """Return True if the SQL string appears to perform a write operation."""
    return bool(WRITE_KEYWORDS.search(sql))


def _extract_table_names(parsed: exp.Expression) -> set[str]:
    """Collect unqualified table names from a parsed SQL expression."""
    tables: set[str] = set()
    for t in parsed.find_all(exp.Table):
        # t.name is unqualified table name
        if t.name:
            tables.add(t.name.lower())
    return tables


def _is_aggregate_query(parsed: exp.Expression) -> bool:
    """Detect whether the query contains aggregate operations or GROUP BY."""
    # If query contains GROUP BY or aggregate function calls (SUM/COUNT/AVG/MIN/MAX)
    if parsed.find(exp.Group) is not None:
        return True

    for func in parsed.find_all(exp.Anonymous):
        if func.name and func.name.upper() in {"SUM", "COUNT", "AVG", "MIN", "MAX"}:
            return True

    # sqlglot uses specific classes for some funcs too
    if parsed.find(exp.Count) or parsed.find(exp.Sum) or parsed.find(exp.Avg) or parsed.find(exp.Min) or parsed.find(exp.Max):
        return True

    return False


def _has_limit(parsed: exp.Expression) -> bool:
    """Check whether the parsed query contains a LIMIT clause."""
    return parsed.find(exp.Limit) is not None


def enforce_sql_safety(sql: str, cfg: Optional[SQLSafetyConfig] = None) -> str:
    """
    Validate and normalize SQL. If safe, returns a possibly modified SQL (adds LIMIT).
    Raises SQLSafetyError if unsafe.
    """
    cfg = cfg or SQLSafetyConfig()

    sql = sql.strip().rstrip(";")
    if not sql:
        raise SQLSafetyError("Empty SQL")

    if is_write_query(sql):
        logger.warning("Rejected write-like SQL")
        raise SQLSafetyError("Write operations are not allowed (read-only mode).")

    try:
        parsed = sqlglot.parse_one(sql, read="mysql")
    except Exception as e:
        logger.error("SQL parse error: %s", e)
        raise SQLSafetyError(f"SQL parse error: {e}") from e

    # Only allow SELECT
    if not isinstance(parsed, exp.Select) and parsed.find(exp.Select) is None:
        logger.warning("Rejected non-select SQL")
        raise SQLSafetyError("Only SELECT queries are allowed.")

    tables = _extract_table_names(parsed)
    allowed = set(t.lower() for t in cfg.allowed_tables)
    disallowed = [t for t in tables if t not in allowed]
    if disallowed:
        logger.warning("Query references disallowed tables: %s", disallowed)
        raise SQLSafetyError(f"Query references disallowed tables: {disallowed}")

    if cfg.require_limit_for_non_aggregate and not _is_aggregate_query(parsed):
        if not _has_limit(parsed):
            # Add LIMIT
            sql = f"{sql} LIMIT {cfg.default_limit}"
            logger.info("Added default LIMIT %s to non-aggregate query", cfg.default_limit)

    return sql + ";"
