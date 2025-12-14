from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional


def rows_to_markdown_table(rows: List[Dict[str, Any]], max_rows: int = 50) -> str:
    if not rows:
        return "_No rows returned._"

    shown = rows[:max_rows]
    cols = list(shown[0].keys())

    def esc(x: Any) -> str:
        s = "" if x is None else str(x)
        return s.replace("|", "\\|").replace("\n", " ")

    header = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    body_lines = [
        "| " + " | ".join(esc(r.get(c)) for c in cols) + " |"
        for r in shown
    ]

    extra = ""
    if len(rows) > max_rows:
        extra = f"\n\n_Showing first {max_rows} of {len(rows)} rows._"

    return "\n".join([header, sep, *body_lines]) + extra
