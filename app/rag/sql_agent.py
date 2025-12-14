from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.rag.sql_safety import SQLSafetyConfig, enforce_sql_safety


@dataclass
class SQLRunResult:
    sql: str
    params: Dict[str, Any]
    rows: List[Dict[str, Any]]
    row_count: int


class SQLAgent:
    def __init__(self, engine: Engine, safety_cfg: Optional[SQLSafetyConfig] = None):
        self.engine = engine
        self.safety_cfg = safety_cfg or SQLSafetyConfig()

    def run_sql(self, sql: str, params: Optional[Dict[str, Any]] = None) -> SQLRunResult:
        params = params or {}
        safe_sql = enforce_sql_safety(sql, self.safety_cfg)
        with self.engine.connect() as conn:
            result = conn.execute(text(safe_sql), params)
            rows = [dict(r._mapping) for r in result.fetchall()]
        return SQLRunResult(sql=safe_sql, params=params, rows=rows, row_count=len(rows))

    def run_sql_df(self, sql: str, params: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any], pd.DataFrame]:
        params = params or {}
        safe_sql = enforce_sql_safety(sql, self.safety_cfg)
        df = pd.read_sql(text(safe_sql), self.engine, params=params)
        return safe_sql, params, df
