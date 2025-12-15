from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.rag.sql_safety import SQLSafetyConfig, enforce_sql_safety

logger = logging.getLogger(__name__)

@dataclass
class SQLRunResult:
    sql: str
    params: Dict[str, Any]
    rows: List[Dict[str, Any]]
    row_count: int
    """Result of executing a SQL query including rows and count."""


class SQLAgent:
    def __init__(self, engine: Engine, safety_cfg: Optional[SQLSafetyConfig] = None):
        """SQL executor that enforces safety checks before running queries."""
        self.engine = engine
        self.safety_cfg = safety_cfg or SQLSafetyConfig()

    def run_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> SQLRunResult:
        """Execute SQL safely with optional parameters, returning structured results."""
        params = params or {}
        safe_sql = enforce_sql_safety(sql, self.safety_cfg)
        logger.info("Executing SQL via SQLAlchemy")
        logger.debug("SQL: %s | params=%s", safe_sql, params)
        with self.engine.connect() as conn:
            result = conn.execute(text(safe_sql), params)
            rows = [dict(r._mapping) for r in result.fetchall()]
        row_count = len(rows)
        logger.info("SQL executed successfully; rows=%s", row_count)
        return SQLRunResult(sql=safe_sql, params=params, rows=rows, row_count=row_count)

    def run_sql_df(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any], pd.DataFrame]:
        """Execute SQL safely and return a pandas DataFrame along with SQL and params."""
        params = params or {}
        safe_sql = enforce_sql_safety(sql, self.safety_cfg)
        logger.info("Executing SQL to DataFrame")
        logger.debug("SQL: %s | params=%s", safe_sql, params)
        df = pd.read_sql(text(safe_sql), self.engine, params=params)
        logger.info("SQL DataFrame rows=%s", len(df))
        return safe_sql, params, df
