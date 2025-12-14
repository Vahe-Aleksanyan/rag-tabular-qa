from __future__ import annotations

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
from app.rag.answer_synth import AnswerSynth


def _norm_value(v: Any) -> Any:
    # Normalize DB-returned values to stable comparisons
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
    """
    Convert list[dict] rows into a sorted, comparable structure.
    """
    normalized = []
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
) -> CheckResult:
    tid = test["id"]
    q = test["question"]
    expect = test.get("expect", {})
    oracle = test.get("oracle")
    assertions = test.get("assertions", {})

    t0 = perf_counter()
    route = router.route(q)
    t1 = perf_counter()

    # 1) Action check
    exp_action = expect.get("action")
    if exp_action and route.action != exp_action:
        return CheckResult(
            tid,
            False,
            f"Action mismatch: expected {exp_action}, got {route.action}. (router_time={(t1-t0):.2f}s)",
        )

    # CLARIFY/REFUSE tests end here (no oracle SQL required)
    if route.action in ("CLARIFY", "REFUSE"):
        return CheckResult(
            tid,
            True,
            f"{route.action} as expected. (router_time={(t1-t0):.2f}s)",
        )

    # 2) Intent check (QUERY only)
    plan = route.plan
    exp_intent = expect.get("intent")
    if exp_intent and plan.intent != exp_intent:
        return CheckResult(tid, False, f"Intent mismatch: expected {exp_intent}, got {plan.intent}")

    # 3) Field checks (subset only)
    exp_fields: Dict[str, Any] = expect.get("fields") or {}
    for k, v in exp_fields.items():
        got = _get_field(plan, k)
        if got != v:
            return CheckResult(tid, False, f"Field mismatch: {k}: expected {v}, got {got}")

    # If no oracle provided, we only check router correctness.
    if not oracle:
        return CheckResult(tid, True, "Router checks passed (no oracle SQL).")

    # 4) Run pipeline SQL (hybrid)
    mode = "deterministic"
    try:
        if plan.intent == "FREEFORM_SQL":
            raise ValueError("Router chose FREEFORM_SQL")
        built = build_sql(plan)
        pipeline_sql, pipeline_params = built.sql, built.params
    except Exception:
        mode = "freeform"
        ff = freeform.generate(q)
        pipeline_sql, pipeline_params = ff.safe_sql, {}

    try:
        pipeline_run = sql_agent.run_sql(pipeline_sql, pipeline_params)
    except Exception as e:
        if mode == "freeform":
            ff2 = freeform.repair(q, pipeline_sql, str(e))
            pipeline_sql, pipeline_params = ff2.safe_sql, {}
            pipeline_run = sql_agent.run_sql(pipeline_sql, pipeline_params)
        else:
            return CheckResult(tid, False, f"Pipeline SQL execution failed: {e}")

    # 5) Run oracle SQL
    oracle_sql = oracle["sql"]
    oracle_params = oracle.get("params") or {}
    try:
        oracle_run = sql_agent.run_sql(oracle_sql, oracle_params)
    except Exception as e:
        return CheckResult(tid, False, f"Oracle SQL execution failed: {e}")

    # 6) Assertions
    min_rows = assertions.get("min_rows")
    if min_rows is not None and len(pipeline_run.rows) < int(min_rows):
        return CheckResult(tid, False, f"min_rows failed: got {len(pipeline_run.rows)} < {min_rows}")

    req_cols = assertions.get("columns") or []
    if req_cols:
        col_err = _ensure_columns(pipeline_run.rows, req_cols)
        if col_err:
            return CheckResult(tid, False, col_err)

    # 7) Result equivalence
    A = _norm_rows(pipeline_run.rows)
    B = _norm_rows(oracle_run.rows)
    if A != B:
        return CheckResult(
            tid,
            False,
            f"Result mismatch vs oracle. pipeline_rows={len(A)} oracle_rows={len(B)} mode={mode}",
        )

    t2 = perf_counter()
    return CheckResult(tid, True, f"PASS. mode={mode} rows={len(A)} total_time={(t2-t0):.2f}s")


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    golden_path = root / "app" / "eval" / "golden.yaml"
    out_path = root / "Eval_Report.md"

    data = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    tests = data["tests"]

    engine = get_engine()
    sql_agent = SQLAgent(engine)

    llm = OpenAIClient()
    router = Router(llm)
    freeform = FreeformSQLGenerator(llm)

    results: List[CheckResult] = []
    for t in tests:
        results.append(run_one_test(t, router=router, sql_agent=sql_agent, freeform=freeform))

    passed = sum(1 for r in results if r.ok)
    total = len(results)

    lines: List[str] = []
    lines.append("# Golden Evaluation Report")
    lines.append("")
    lines.append(f"Passed: **{passed}/{total}**")
    lines.append("")
    lines.append("| Test ID | Status | Details |")
    lines.append("|---|---|---|")
    for r in results:
        status = "✅ PASS" if r.ok else "❌ FAIL"
        details = r.details.replace("\n", "<br>").replace("|", "\\|")
        lines.append(f"| `{r.id}` | {status} | {details} |")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    main()
