from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from app.llm.openai_client import OpenAIClient
from app.rag.sql_safety import enforce_sql_safety
from app.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SQL_SYSTEM = load_prompt("freeform_sql_system.txt")
REPAIR_SYSTEM = load_prompt("freeform_sql_repair_system.txt")


@dataclass(frozen=True)
class FreeformSQL:
    raw_sql: str
    safe_sql: str
    """SQL outputs with raw and safety-enforced variants."""


class FreeformSQLGenerator:
    def __init__(self, llm: OpenAIClient):
        """Create a freeform SQL generator using the provided LLM client."""
        self.llm = llm

    def generate(self, question: str) -> FreeformSQL:
        """
        Generate SQL directly from a natural-language question, enforcing safety rules.
        """
        logger.info("Generating freeform SQL")
        raw = self.llm.text(SQL_SYSTEM, f"Question: {question}").strip().rstrip(";")
        safe = enforce_sql_safety(raw)
        logger.debug("Generated SQL (safe applied)")
        return FreeformSQL(raw_sql=raw + ";", safe_sql=safe)

    def repair(self, question: str, previous_sql: str, error: str) -> FreeformSQL:
        """
        Repair a failed SQL attempt using the LLM and re-apply safety checks.
        """
        logger.info("Repairing SQL after failure: %s", error)
        user = (
            f"Question: {question}\n\n"
            f"Failed SQL:\n{previous_sql}\n\n"
            f"Error:\n{error}\n\n"
            "Return a corrected SQL query."
        )
        raw = self.llm.text(REPAIR_SYSTEM, user).strip().rstrip(";")
        safe = enforce_sql_safety(raw)
        logger.debug("Repaired SQL generated (safe applied)")
        return FreeformSQL(raw_sql=raw + ";", safe_sql=safe)
