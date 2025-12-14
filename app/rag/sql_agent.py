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
    rows: List[Dict[str, Any]]
    row_count: int


class SQLAgent:
    def __init__(self, engine: Engine, safety_cfg: Optional[SQLSafetyConfig] = None):
        self.engine = engine
        self.safety_cfg = safety_cfg or SQLSafetyConfig()

    def run_sql(self, sql: str) -> SQLRunResult:
        safe_sql = enforce_sql_safety(sql, self.safety_cfg)
        with self.engine.connect() as conn:
            result = conn.execute(text(safe_sql))
            rows = [dict(r._mapping) for r in result.fetchall()]
        return SQLRunResult(sql=safe_sql, rows=rows, row_count=len(rows))

    def run_sql_df(self, sql: str) -> Tuple[str, pd.DataFrame]:
        safe_sql = enforce_sql_safety(sql, self.safety_cfg)
        df = pd.read_sql(text(safe_sql), self.engine)
        return safe_sql, df
