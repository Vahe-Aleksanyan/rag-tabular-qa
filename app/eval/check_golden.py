from __future__ import annotations

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, List, Optional, Tuple

import yaml

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql
from app.rag.freeform_sql import FreeformSQLGenerator
from app.utils.logging import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

def safe_model_name(model: str) -> str:
    return model.strip().lower().replace("/", "_").replace(":", "_").replace(".", "_")


def _norm_value(v: Any) -> Any:
    if v is None:
        return None

    # decimals from SQLAlchemy/MySQL can show up as Decimal
    try:
        from decimal import Decimal

        if isinstance(v, Decimal):
            return round(float(v), 6)
    except Exception:
        pass

    if isinstance(v, float):
        return round(v, 6)

    # dates might come as date/datetime objects
    try:
        import datetime as dt

        if isinstance(v, (dt.date, dt.datetime)):
            return v.isoformat()
    except Exception:
        pass

    return v


def _norm_rows(rows: List[Dict[str, Any]]) -> List[Tuple[Tuple[str, Any], ...]]:
    normalized: List[Tuple[Tuple[str, Any], ...]] = []
    for r in rows:
        items = tuple(sorted((k, _norm_value(v)) for k, v in r.items()))
        normalized.append(items)
    normalized.sort()
    return normalized


def _ensure_columns(rows: List[Dict[str, Any]], required: List[str]) -> Optional[str]:
    if not rows:
        return None
    present = set(rows[0].keys())
    missing = [c for c in required if c not in present]
    if missing:
        return f"Missing columns: {missing}. Present: {sorted(present)}"
    return None


def _diff_preview(
    A: List[Tuple[Tuple[str, Any], ...]],
    B: List[Tuple[Tuple[str, Any], ...]],
    limit: int = 3,
) -> str:
    """
    Small diagnostic: show first few items that differ, stable order.
    """
    setA = set(A)
    setB = set(B)
    onlyA = sorted(list(setA - setB))[:limit]
    onlyB = sorted(list(setB - setA))[:limit]
    parts = []
    if onlyA:
        parts.append(f"only_in_pipeline={onlyA}")
    if onlyB:
        parts.append(f"only_in_oracle={onlyB}")
    return "; ".join(parts) if parts else "no_diff_preview"


@dataclass
class CheckResult:
    id: str
    ok: bool
    details: str


def _get_field(plan, name: str) -> Any:
    return getattr(plan, name, None)


def run_one_test(
    test: Dict[str, Any],
    *,
    router: Router,
    sql_agent: SQLAgent,
    freeform: FreeformSQLGenerator,
) -> Tuple[CheckResult, Dict[str, Any]]:
    """
    Returns (CheckResult, meta) where meta is for summary stats.
    """
    tid = test["id"]
    q = test["question"]
    logger.debug("Running golden test: id=%s", tid)
    expect = test.get("expect", {})
    oracle = test.get("oracle")
    assertions = test.get("assertions", {})

    meta: Dict[str, Any] = {
        "mode": None,
        "repair": False,
        "router_s": 0.0,
        "sql_s": 0.0,
        "total_s": 0.0,
        "pipeline_rows": None,
    }

    t0 = perf_counter()

    # 1) Router
    r0 = perf_counter()
    route = router.route(q)
    r1 = perf_counter()
    meta["router_s"] = r1 - r0

    # 2) Action check
    exp_action = expect.get("action")
    if exp_action and route.action != exp_action:
        t1 = perf_counter()
        meta["total_s"] = t1 - t0
        logger.warning(
            "Action mismatch: id=%s expected=%s got=%s router_time=%.2fs",
            tid,
            exp_action,
            route.action,
            r1 - r0,
        )
        return (
            CheckResult(
                tid,
                False,
                f"Action mismatch: expected {exp_action}, got {route.action}. (router_time={(r1-r0):.2f}s)",
            ),
            meta,
        )

    # CLARIFY/REFUSE tests end here (no oracle SQL required)
    if route.action in ("CLARIFY", "REFUSE"):
        meta["mode"] = route.action.lower()
        t1 = perf_counter()
        meta["total_s"] = t1 - t0
        logger.info(
            "Non-query action: id=%s action=%s router_time=%.2fs",
            tid,
            route.action,
            r1 - r0,
        )
        return (
            CheckResult(tid, True, f"{route.action} as expected. (router_time={(r1-r0):.2f}s)"),
            meta,
        )

    # 3) Intent check (QUERY only)
    plan = route.plan
    exp_intent = expect.get("intent")
    if exp_intent and plan.intent != exp_intent:
        t1 = perf_counter()
        meta["total_s"] = t1 - t0
        logger.warning("Intent mismatch: id=%s expected=%s got=%s", tid, exp_intent, plan.intent)
        return (CheckResult(tid, False, f"Intent mismatch: expected {exp_intent}, got {plan.intent}"), meta)

    # 4) Field checks (subset only)
    exp_fields: Dict[str, Any] = expect.get("fields") or {}
    for k, v in exp_fields.items():
        got = _get_field(plan, k)
        if got != v:
            t1 = perf_counter()
            meta["total_s"] = t1 - t0
            logger.warning("Field mismatch: id=%s field=%s expected=%s got=%s", tid, k, v, got)
            return (CheckResult(tid, False, f"Field mismatch: {k}: expected {v}, got {got}"), meta)

    # If no oracle provided, we only check router correctness.
    if not oracle:
        t1 = perf_counter()
        meta["total_s"] = t1 - t0
        return (CheckResult(tid, True, "Router checks passed (no oracle SQL)."), meta)

    # 5) Run pipeline SQL (hybrid)
    mode = "deterministic"
    repair_used = False

    try:
        if plan.intent == "FREEFORM_SQL":
            raise ValueError("Router chose FREEFORM_SQL")
        built = build_sql(plan)
        pipeline_sql, pipeline_params = built.sql, built.params
    except Exception:
        mode = "freeform"
        ff = freeform.generate(q)
        pipeline_sql, pipeline_params = ff.safe_sql, {}
        logger.info("Freeform fallback used for id=%s", tid)

    # 6) Execute pipeline SQL (with one repair in freeform mode)
    s0 = perf_counter()
    try:
        pipeline_run = sql_agent.run_sql(pipeline_sql, pipeline_params)
    except Exception as e:
        if mode == "freeform":
            repair_used = True
            ff2 = freeform.repair(q, pipeline_sql, str(e))
            pipeline_sql, pipeline_params = ff2.safe_sql, {}
            pipeline_run = sql_agent.run_sql(pipeline_sql, pipeline_params)
            logger.info("Freeform repair used for id=%s after error: %s", tid, e)
        else:
            s1 = perf_counter()
            meta["mode"] = mode
            meta["repair"] = repair_used
            meta["sql_s"] = s1 - s0
            meta["pipeline_rows"] = None
            meta["total_s"] = perf_counter() - t0
            logger.error("Pipeline SQL failed for id=%s: %s", tid, e, exc_info=True)
            return (CheckResult(tid, False, f"Pipeline SQL execution failed: {e}"), meta)
    s1 = perf_counter()

    meta["mode"] = mode
    meta["repair"] = repair_used
    meta["sql_s"] = s1 - s0
    meta["pipeline_rows"] = len(pipeline_run.rows)

    # 7) Run oracle SQL
    oracle_sql = oracle["sql"]
    oracle_params = oracle.get("params") or {}
    try:
        oracle_run = sql_agent.run_sql(oracle_sql, oracle_params)
    except Exception as e:
        meta["total_s"] = perf_counter() - t0
        logger.error("Oracle SQL failed for id=%s: %s", tid, e, exc_info=True)
        return (CheckResult(tid, False, f"Oracle SQL execution failed: {e}"), meta)

    # 8) Assertions
    min_rows = assertions.get("min_rows")
    if min_rows is not None and len(pipeline_run.rows) < int(min_rows):
        meta["total_s"] = perf_counter() - t0
        logger.warning("min_rows failed for id=%s: got=%s expected>=%s", tid, len(pipeline_run.rows), min_rows)
        return (CheckResult(tid, False, f"min_rows failed: got {len(pipeline_run.rows)} < {min_rows}"), meta)

    req_cols = assertions.get("columns") or []
    if req_cols:
        col_err = _ensure_columns(pipeline_run.rows, req_cols)
        if col_err:
            meta["total_s"] = perf_counter() - t0
            logger.warning("Column assertion failed for id=%s: %s", tid, col_err)
            return (CheckResult(tid, False, col_err), meta)

    # 9) Result equivalence
    A = _norm_rows(pipeline_run.rows)
    B = _norm_rows(oracle_run.rows)
    if A != B:
        preview = _diff_preview(A, B, limit=3)
        meta["total_s"] = perf_counter() - t0
        logger.warning(
            "Result mismatch for id=%s: pipeline_rows=%s oracle_rows=%s mode=%s preview=%s",
            tid,
            len(A),
            len(B),
            mode,
            preview,
        )
        return (
            CheckResult(
                tid,
                False,
                f"Result mismatch vs oracle. pipeline_rows={len(A)} oracle_rows={len(B)} mode={mode}. {preview}",
            ),
            meta,
        )

    meta["total_s"] = perf_counter() - t0
    logger.info(
        "PASS id=%s mode=%s rows=%s time=%.2fs repair=%s",
        tid,
        mode,
        len(A),
        meta["total_s"],
        repair_used,
    )
    return (CheckResult(tid, True, f"PASS. mode={mode} rows={len(A)} total_time={meta['total_s']:.2f}s"), meta)


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    golden_path = root / "app" / "eval" / "golden.yaml"

    model = os.getenv("OPENAI_MODEL", "unknown-model")
    out_path = root / f"Eval_Report.{safe_model_name(model)}.md"

    data = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    tests = data["tests"]
    logger.info("Starting golden checks: model=%s tests=%s", model, len(tests))

    engine = get_engine()
    sql_agent = SQLAgent(engine)

    llm = OpenAIClient()
    router = Router(llm)
    freeform = FreeformSQLGenerator(llm)

    results: List[CheckResult] = []
    metas: List[Dict[str, Any]] = []

    for t in tests:
        res, meta = run_one_test(t, router=router, sql_agent=sql_agent, freeform=freeform)
        results.append(res)
        metas.append(meta)
        logger.info("Test result: id=%s status=%s mode=%s time=%.2fs", res.id, "PASS" if res.ok else "FAIL", meta.get("mode"), meta.get("total_s"))

    passed = sum(1 for r in results if r.ok)
    total = len(results)

    # Summary stats (QUERY only)
    query_metas = [m for m in metas if m.get("mode") in ("deterministic", "freeform")]
    n_query = len(query_metas)
    n_freeform = sum(1 for m in query_metas if m.get("mode") == "freeform")
    n_repair = sum(1 for m in query_metas if m.get("repair") is True)

    avg_total = sum(m["total_s"] for m in query_metas) / n_query if n_query else 0.0
    avg_router = sum(m["router_s"] for m in query_metas) / n_query if n_query else 0.0
    avg_sql = sum(m["sql_s"] for m in query_metas) / n_query if n_query else 0.0

    lines: List[str] = []
    lines.append("# Golden Evaluation Report")
    lines.append("")
    lines.append(f"- Model: `{model}`")
    lines.append(f"- Passed: **{passed}/{total}**")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- QUERY tests: **{n_query}**")
    lines.append(f"- Freeform used (QUERY): **{n_freeform}/{n_query}**")
    lines.append(f"- Freeform repair used (QUERY): **{n_repair}/{n_query}**")
    if n_query:
        lines.append(
            f"- Avg timings (QUERY): total={avg_total:.2f}s, router={avg_router:.2f}s, sql={avg_sql:.2f}s"
        )
    lines.append("")
    lines.append("| Test ID | Status | Details |")
    lines.append("|---|---|---|")
    for r in results:
        status = "✅ PASS" if r.ok else "❌ FAIL"
        details = r.details.replace("\n", "<br>").replace("|", "\\|")
        lines.append(f"| `{r.id}` | {status} | {details} |")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "Golden checks complete: passed=%s total=%s query=%s freeform=%s repair=%s output=%s",
        passed,
        total,
        n_query,
        n_freeform,
        n_repair,
        out_path,
    )
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
