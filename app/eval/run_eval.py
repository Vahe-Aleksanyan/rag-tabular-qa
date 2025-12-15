from __future__ import annotations

import os
import logging
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
from app.utils.logging import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def md_escape(s: str) -> str:
    # Markdown table-safe rendering
    return str(s).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")


def safe_model_name(model: str) -> str:
    # filename-safe model id
    return model.strip().lower().replace("/", "_").replace(":", "_").replace(".", "_")


@dataclass
class EvalRow:
    question: str
    answer: str


@dataclass
class Timing:
    router_s: float
    sql_s: float
    synth_s: float
    total_s: float


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
) -> Tuple[EvalRow, Timing, str, bool]:
    """
    Returns:
      - EvalRow
      - Timing(router/sql/synth/total)
      - mode ("deterministic"|"freeform"|"clarify"|"refuse")
      - repair_used (bool)
    """
    t0 = perf_counter()

    # 1) Route
    r0 = perf_counter()
    route = router.route(q)
    r1 = perf_counter()

    # Router-driven refusal/clarify
    if route.action == "REFUSE":
        msg = route.refusal_message or "Refused (out of domain)."
        t1 = perf_counter()
        row = EvalRow(question=q, answer=f"Mode: refuse. {msg}")
        timing = Timing(router_s=r1 - r0, sql_s=0.0, synth_s=0.0, total_s=t1 - t0)
        return row, timing, "refuse", False

    if route.action == "CLARIFY":
        msg = route.clarifying_question or "Clarification needed."
        missing = ", ".join(route.missing_fields) if route.missing_fields else "unspecified"
        t1 = perf_counter()
        row = EvalRow(question=q, answer=f"Mode: clarify. {msg} (missing: {missing})")
        timing = Timing(router_s=r1 - r0, sql_s=0.0, synth_s=0.0, total_s=t1 - t0)
        return row, timing, "clarify", False

    plan = route.plan
    mode = "deterministic"
    repair_used = False

    # 2) Build SQL (hybrid)
    try:
        if plan.intent == "FREEFORM_SQL":
            raise ValueError("Router chose FREEFORM_SQL")
        built = build_sql(plan)
        sql_text, params = built.sql, built.params
    except Exception:
        mode = "freeform"
        ff = freeform.generate(q)
        sql_text, params = ff.safe_sql, {}

    # 3) Execute SQL (with one repair in freeform)
    s0 = perf_counter()
    try:
        run = sql_agent.run_sql(sql_text, params)
    except Exception as e:
        if mode == "freeform":
            repair_used = True
            ff2 = freeform.repair(q, sql_text, str(e))
            sql_text, params = ff2.safe_sql, {}
            run = sql_agent.run_sql(sql_text, params)
        else:
            raise
    s1 = perf_counter()

    # 4) Synthesize narrative
    a0 = perf_counter()
    narrative = synth.synthesize(q, run.sql, run.rows)
    a1 = perf_counter()

    t1 = perf_counter()

    timing = Timing(
        router_s=r1 - r0,
        sql_s=s1 - s0,
        synth_s=a1 - a0,
        total_s=t1 - t0,
    )

    # Short reviewer-friendly meta prefix
    meta = (
        f"Mode: {mode}. rows={len(run.rows)}. "
        f"time={timing.total_s:.2f}s (router={timing.router_s:.2f}s, sql={timing.sql_s:.2f}s, synth={timing.synth_s:.2f}s). "
        f"repair={'yes' if repair_used else 'no'}."
    )

    row = EvalRow(question=q, answer=f"{meta} {narrative}")
    return row, timing, mode, repair_used


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    questions_path = root / "app" / "eval" / "questions.yaml"

    model = os.getenv("OPENAI_MODEL", "unknown-model")
    out_path = root / f"Test_Results_Table.{safe_model_name(model)}.md"

    data = yaml.safe_load(questions_path.read_text(encoding="utf-8"))
    items = flatten_questions(data)
    logger.info("Starting eval: model=%s questions=%s", model, len(items))

    engine = get_engine()
    sql_agent = SQLAgent(engine)

    llm = OpenAIClient()
    router = Router(llm)
    synth = AnswerSynth(llm)
    freeform = FreeformSQLGenerator(llm)

    # Aggregate stats (nice in README)
    n = 0
    n_query = 0
    n_refuse = 0
    n_clarify = 0
    n_freeform = 0
    n_repair = 0
    total_time = 0.0
    total_router = 0.0
    total_sql = 0.0
    total_synth = 0.0

    lines: List[str] = []
    lines.append("# Test Results Table")
    lines.append("")
    lines.append(f"- Model: `{model}`")
    lines.append("")

    lines.append("| Question | Answer |")
    lines.append("|---|---|")

    for section, q in items:
        n += 1
        try:
            row, timing, mode, repair_used = run_one_question(
                q,
                router=router,
                sql_agent=sql_agent,
                synth=synth,
                freeform=freeform,
            )
            logger.info(
                "Q%s done: section=%s mode=%s repair=%s time=%.2fs",
                n,
                section,
                mode,
                repair_used,
                timing.total_s if mode not in {"refuse", "clarify"} else 0.0,
            )

            if mode == "refuse":
                n_refuse += 1
            elif mode == "clarify":
                n_clarify += 1
            else:
                n_query += 1
                if mode == "freeform":
                    n_freeform += 1
                if repair_used:
                    n_repair += 1
                total_time += timing.total_s
                total_router += timing.router_s
                total_sql += timing.sql_s
                total_synth += timing.synth_s

            q_cell = f"[{section}] {row.question}"
            lines.append(f"| {md_escape(q_cell)} | {md_escape(row.answer)} |")

        except Exception as e:
            q_cell = f"[{section}] {q}"
            lines.append(f"| {md_escape(q_cell)} | {md_escape(f'ERROR: {e}')} |")
            logger.error("Failed to evaluate question %s (%s): %s", n, section, e, exc_info=True)

    # Summary (still complies: table remains two columns; this is outside table)
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Total questions: **{n}**")
    lines.append(f"- QUERY: **{n_query}**, CLARIFY: **{n_clarify}**, REFUSE: **{n_refuse}**")
    if n_query:
        denom = float(n_query)
        lines.append(f"- Freeform used (among QUERY): **{n_freeform}/{n_query}**")
        lines.append(f"- Freeform repair used (among QUERY): **{n_repair}/{n_query}**")
        lines.append(
            f"- Avg time (QUERY only): **{(total_time/denom):.2f}s** "
            f"(router={(total_router/denom):.2f}s, sql={(total_sql/denom):.2f}s, synth={(total_synth/denom):.2f}s)"
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "Eval complete: total=%s query=%s clarify=%s refuse=%s freeform=%s repair=%s output=%s",
        n,
        n_query,
        n_clarify,
        n_refuse,
        n_freeform,
        n_repair,
        out_path,
    )
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
