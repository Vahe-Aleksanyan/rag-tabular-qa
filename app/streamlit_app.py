from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional, Tuple

import streamlit as st

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql
from app.rag.answer_synth import AnswerSynth
from app.utils.formatting import rows_to_markdown_table
from app.rag.freeform_sql import FreeformSQLGenerator


# -----------------------------
# Helpers
# -----------------------------
def normalize_question(q: str) -> str:
    return " ".join(q.strip().lower().split())


def append_assistant(
    content: str,
    *,
    mode: str,
    table_md: Optional[str] = None,
    sql: Optional[str] = None,
    rows: Optional[list[dict]] = None,
    show_sql: bool = False,
    show_rows: bool = False,
) -> None:
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": content,
            "mode": mode,
            "table_md": table_md,
            "sql": sql,
            "rows": rows,
            "show_sql": show_sql,
            "show_rows": show_rows,
        }
    )


def render_message(m: Dict[str, Any]) -> None:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant" and m.get("mode"):
            st.caption(f"Mode: {m['mode']}")
        st.markdown(m["content"])

        if m.get("table_md"):
            st.markdown(m["table_md"])
        if m.get("show_sql") and m.get("sql"):
            st.code(m["sql"], language="sql")
        if m.get("show_rows") and m.get("rows"):
            st.json(m["rows"])


def fill_pending(plan, field: str, user_text: str):
    """
    Minimal parser for clarification replies.
    Kept small and generic; intent-specific rules should live in the router (best),
    but this keeps your current approach working.
    """
    txt = user_text.strip()

    if field in {"invoice_id", "country", "client_name", "as_of_date", "service_name"}:
        setattr(plan, field, txt)
        return plan

    if field == "year":
        plan.year = int(re.search(r"(20\d{2})", txt).group(1)) if re.search(r"(20\d{2})", txt) else int(txt)
        return plan

    if field == "month":
        m = re.search(r"\b(1[0-2]|[1-9])\b", txt)
        if not m:
            raise ValueError("Could not parse month. Use 1-12.")
        plan.month = int(m.group(1))
        return plan

    if field == "month_year":
        y = re.search(r"(20\d{2})", txt)
        if y:
            plan.year = int(y.group(1))
        m = re.search(r"\b(1[0-2]|[1-9])\b", txt)
        if m:
            plan.month = int(m.group(1))
        return plan

    # Unknown field - just store raw text somewhere if you want
    return plan


# -----------------------------
# UI config
# -----------------------------
st.set_page_config(page_title="Tabular QA", layout="wide")
st.title("Tabular QA — Chat over Excel → MySQL")

st.sidebar.header("LLM")
default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
model = st.sidebar.text_input("OpenAI model", value=default_model)
if st.sidebar.button("Apply model"):
    os.environ["OPENAI_MODEL"] = model
    st.sidebar.success(f"Using model: {model}")

show_sql = st.sidebar.checkbox("Show SQL", value=True)
show_rows = st.sidebar.checkbox("Show retrieved rows (JSON)", value=False)

if st.sidebar.button("Clear chat"):
    st.session_state.messages = []
    st.session_state.plan_cache = {}
    st.session_state.pending = None
    st.rerun()


# -----------------------------
# App dependencies
# -----------------------------
engine = get_engine()
sql_agent = SQLAgent(engine)

llm = OpenAIClient()
router = Router(llm)
synth = AnswerSynth(llm)
freeform = FreeformSQLGenerator(llm)


# -----------------------------
# Session state
# -----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "plan_cache" not in st.session_state:
    st.session_state.plan_cache = {}
if "pending" not in st.session_state:
    st.session_state.pending = None  # {"orig_question": "..."} or None


# -----------------------------
# Replay chat history
# -----------------------------
for m in st.session_state.messages:
    render_message(m)


# -----------------------------
# Main loop
# -----------------------------
question = st.chat_input("Ask about clients, invoices, line items...")

if not question:
    st.stop()

# store + render user message
st.session_state.messages.append({"role": "user", "content": question})
with st.chat_message("user"):
    st.markdown(question)

# 1) Get plan (router also handles clarifications/refusals)
try:
    route_input = question
    if st.session_state.pending:
        # Provide the original question plus the user's clarification back to the router.
        route_input = f"{st.session_state.pending['orig_question']}\n\nUser clarification: {question}"
        st.session_state.pending = None

    key = normalize_question(route_input)
    if key in st.session_state.plan_cache:
        plan = st.session_state.plan_cache[key]
    else:
        route = router.route(route_input)
        if route.action == "REFUSE":
            msg = route.refusal_message or (
                "I can only answer questions about the business tables: clients, invoices, and invoice line items."
            )
            with st.chat_message("assistant"):
                st.warning(msg)
            append_assistant(msg, mode="guard")
            st.stop()

        if route.action == "CLARIFY":
            msg = route.clarifying_question or "I need one detail to answer. Can you clarify?"
            with st.chat_message("assistant"):
                st.info(msg)
            append_assistant(msg, mode="clarify")
            st.session_state.pending = {"orig_question": route_input}
            st.stop()

        if not route.plan:
            raise ValueError("Router returned QUERY without a plan.")

        plan = route.plan
        st.session_state.plan_cache[key] = plan
    used_mode_hint = "deterministic"
except Exception as e:
    msg = f"I couldn't parse that clarification. {e}"
    with st.chat_message("assistant"):
        st.info(msg)
    append_assistant(msg, mode="clarify")
    st.stop()

# 2) Hybrid SQL selection with stability guard
# - Deterministic if intent != FREEFORM_SQL and builder supports it
# - Freeform only if router explicitly requested it OR builder unsupported
used_mode = "deterministic"
sql_text: str
sql_params: Dict[str, Any]

if plan.intent == "FREEFORM_SQL":
    used_mode = "freeform"
    ff = freeform.generate(question)
    sql_text, sql_params = ff.safe_sql, {}
else:
    try:
        built = build_sql(plan)
        sql_text, sql_params = built.sql, built.params
    except ValueError:
        used_mode = "freeform"
        ff = freeform.generate(question)
        sql_text, sql_params = ff.safe_sql, {}

# 3) Execute with one repair attempt in freeform mode
try:
    run = sql_agent.run_sql(sql_text, sql_params)
except Exception as e:
    if used_mode == "freeform":
        ff2 = freeform.repair(question, sql_text, str(e))
        sql_text, sql_params = ff2.safe_sql, {}
        run = sql_agent.run_sql(sql_text, sql_params)
    else:
        raise

# 4) Synthesize answer + deterministic table
narrative = synth.synthesize(question, run.sql, run.rows)
table_md = rows_to_markdown_table(run.rows)

# 5) Render + persist assistant
with st.chat_message("assistant"):
    st.caption(f"Mode: {used_mode}")
    st.markdown(narrative)
    st.markdown(table_md)
    if show_sql:
        st.code(f"{run.sql}\n-- params: {run.params}", language="sql")
    if show_rows:
        st.json(run.rows[:50])

append_assistant(
    narrative,
    mode=used_mode,
    table_md=table_md,
    sql=f"{run.sql}\n-- params: {run.params}",
    rows=run.rows[:50],
    show_sql=show_sql,
    show_rows=show_rows,
)
