from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Tuple

import yaml

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql
from app.rag.freeform_sql import FreeformSQLGenerator
from app.rag.answer_synth import AnswerSynth


def md_escape(s: str) -> str:
    # Markdown table-safe rendering
    return (
        str(s)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("\n", "<br>")
    )


@dataclass
class EvalRow:
    question: str
    answer: str


def flatten_questions(data: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Returns list of (section, question) in a stable order.
    """
    out: List[Tuple[str, str]] = []
    for section in ["task_questions", "paraphrases", "robustness"]:
        for q in data.get(section, []) or []:
            out.append((section, q))
    return out


def run_one_question(
    q: str,
    *,
    router: Router,
    sql_agent: SQLAgent,
    synth: AnswerSynth,
    freeform: FreeformSQLGenerator,
) -> EvalRow:
    t0 = perf_counter()
    route = router.route(q)

    # Router-driven refusal/clarify
    if route.action == "REFUSE":
        msg = route.refusal_message or "Refused (out of domain)."
        return EvalRow(question=q, answer=f"Mode: refuse. {msg}")

    if route.action == "CLARIFY":
        msg = route.clarifying_question or "Clarification needed."
        missing = ", ".join(route.missing_fields) if route.missing_fields else "unspecified"
        return EvalRow(question=q, answer=f"Mode: clarify. {msg} (missing: {missing})")

    plan = route.plan
    mode = "deterministic"

    # Hybrid: deterministic first unless FREEFORM_SQL or unsupported
    try:
        if plan.intent == "FREEFORM_SQL":
            raise ValueError("Router chose FREEFORM_SQL")
        built = build_sql(plan)
        sql_text, params = built.sql, built.params
    except Exception:
        mode = "freeform"
        ff = freeform.generate(q)
        sql_text, params = ff.safe_sql, {}

    # Execute with one repair in freeform mode
    try:
        run = sql_agent.run_sql(sql_text, params)
    except Exception as e:
        if mode == "freeform":
            ff2 = freeform.repair(q, sql_text, str(e))
            sql_text, params = ff2.safe_sql, {}
            run = sql_agent.run_sql(sql_text, params)
        else:
            raise

    narrative = synth.synthesize(q, run.sql, run.rows)
    t1 = perf_counter()

    # Keep answer short-ish but informative for reviewers
    meta = f"Mode: {mode}. rows={len(run.rows)}. time={(t1 - t0):.2f}s."
    return EvalRow(question=q, answer=f"{meta} {narrative}")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    questions_path = root / "app" / "eval" / "questions.yaml"
    out_path = root / "Test_Results_Table.md"

    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    items = flatten_questions(data)

    engine = get_engine()
    sql_agent = SQLAgent(engine)

    llm = OpenAIClient()
    router = Router(llm)
    synth = AnswerSynth(llm)
    freeform = FreeformSQLGenerator(llm)

    lines: List[str] = []
    lines.append("# Test Results Table")
    lines.append("")
    lines.append("| Question | Answer |")
    lines.append("|---|---|")

    # Write in order (task first), but keep the “two columns” requirement.
    for section, q in items:
        try:
            row = run_one_question(
                q,
                router=router,
                sql_agent=sql_agent,
                synth=synth,
                freeform=freeform,
            )
            # Prefix section in the Question cell (still 2 columns)
            q_cell = f"[{section}] {row.question}"
            lines.append(f"| {md_escape(q_cell)} | {md_escape(row.answer)} |")
        except Exception as e:
            q_cell = f"[{section}] {q}"
            lines.append(f"| {md_escape(q_cell)} | {md_escape(f'ERROR: {e}')} |")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
