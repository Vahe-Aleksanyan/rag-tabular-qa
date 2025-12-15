from __future__ import annotations

import logging
import json
import re
from typing import Any, Dict, List, Optional

from app.llm.openai_client import OpenAIClient
from app.utils.prompt_loader import load_prompt

logger = logging.getLogger(__name__)

SYSTEM = load_prompt("answer_synth_system.txt")


_NUM_RE = re.compile(r"(?<![A-Za-z])(\d+([.,]\d+)?)")


def _numbers_in_text(s: str) -> set[str]:
    """Return all numeric substrings found in the given text."""
    return set(m.group(1) for m in _NUM_RE.finditer(s))


def _numbers_in_rows(rows: List[Dict[str, Any]]) -> set[str]:
    """Return all numeric substrings found within a JSON dump of result rows."""
    blob = json.dumps(rows, default=str)
    return _numbers_in_text(blob)


class AnswerSynth:
    def __init__(self, llm: OpenAIClient):
        """Create an answer synthesizer using the provided LLM client."""
        self.llm = llm

    def synthesize(self, question: str, sql: str, rows: List[Dict[str, Any]]) -> str:
        """
        Use the LLM to synthesize a natural-language answer from SQL results, enforcing
        that no unsupported numeric values are introduced.
        """
        logger.info("Synthesizing answer for question; rows=%s", len(rows))
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
            logger.warning("LLM introduced unsupported numbers: %s", sorted(extra))
            fix_user = (
                f"Your previous answer included numbers not present in the SQL rows: {sorted(extra)}.\n"
                "Rewrite the answer with NO unsupported numbers. If you need to refer to quantities, say 'see table'.\n\n"
                f"Question:\n{question}\n\n"
                f"SQL executed:\n{sql}\n\n"
                f"Rows (JSON):\n{json.dumps(rows[:50], default=str, ensure_ascii=False)}\n"
            )
            answer = self.llm.text(SYSTEM, fix_user).strip()

        logger.info("Answer synthesized successfully")
        return answer
