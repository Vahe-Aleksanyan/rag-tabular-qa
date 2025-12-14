from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from app.llm.openai_client import OpenAIClient


SYSTEM = """You answer questions about business tables.
Rules (VERY IMPORTANT):
- Use ONLY the provided SQL result rows as your source of truth.
- Do NOT invent any numbers, totals, IDs, dates, currencies, or counts not present in the rows.
- If the rows are empty, say you couldn't find matching records.
- Keep it short: 3-6 sentences.
- Do not output a table. The application will render the table itself.
"""


_NUM_RE = re.compile(r"(?<![A-Za-z])(\d+([.,]\d+)?)")


def _numbers_in_text(s: str) -> set[str]:
    return set(m.group(1) for m in _NUM_RE.finditer(s))


def _numbers_in_rows(rows: List[Dict[str, Any]]) -> set[str]:
    blob = json.dumps(rows, default=str)
    return _numbers_in_text(blob)


class AnswerSynth:
    def __init__(self, llm: OpenAIClient):
        self.llm = llm

    def synthesize(self, question: str, sql: str, rows: List[Dict[str, Any]]) -> str:
        user = (
            f"Question:\n{question}\n\n"
            f"SQL executed:\n{sql}\n\n"
            f"Rows (JSON):\n{json.dumps(rows[:50], default=str, ensure_ascii=False)}\n\n"
            "Write the final answer following the rules."
        )
        answer = self.llm.text(SYSTEM, user).strip()

        # Simple numeric guard: if answer introduces numbers not present in rows, force a correction
        allowed = _numbers_in_rows(rows)
        used = _numbers_in_text(answer)
        extra = used - allowed

        if extra:
            fix_user = (
                f"Your previous answer included numbers not present in the SQL rows: {sorted(extra)}.\n"
                "Rewrite the answer with NO unsupported numbers. If you need to refer to quantities, say 'see table'.\n\n"
                f"Question:\n{question}\n\n"
                f"SQL executed:\n{sql}\n\n"
                f"Rows (JSON):\n{json.dumps(rows[:50], default=str, ensure_ascii=False)}\n"
            )
            answer = self.llm.text(SYSTEM, fix_user).strip()

        return answer
