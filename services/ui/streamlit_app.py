from __future__ import annotations

import os
import logging
from typing import Any, Dict, Optional

import requests
import streamlit as st

from app.utils.formatting import rows_to_markdown_table

from app.utils.logging import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

# -----------------------------
# Helpers
# -----------------------------
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


def render_message(m: Dict[str, Any], *, show_sql: bool, show_rows: bool) -> None:
    with st.chat_message(m["role"]):
        if m["role"] == "assistant" and m.get("mode"):
            st.caption(f"Mode: {m['mode']}")
        st.markdown(m["content"])

        if m.get("table_md"):
            st.markdown(m["table_md"])
        # Use current toggles, not stored toggles (simpler UX)
        if show_sql and m.get("sql"):
            st.code(m["sql"], language="sql")
        if show_rows and m.get("rows"):
            st.json(m["rows"])


def api_post_chat(api_url: str, question: str, timeout: int = 120) -> Dict[str, Any]:
    r = requests.post(f"{api_url}/chat", json={"question": question}, timeout=timeout)
    r.raise_for_status()
    return r.json()


# -----------------------------
# UI config
# -----------------------------
st.set_page_config(page_title="Tabular QA", layout="wide")
st.title("Tabular QA — UI (Streamlit) → API (FastAPI) → MySQL")

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")

st.sidebar.header("Backend")
st.sidebar.code(API_URL)
logger.info("Streamlit UI initialized with API_URL=%s", API_URL)

show_sql = st.sidebar.checkbox("Show SQL", value=True)
show_rows = st.sidebar.checkbox("Show retrieved rows (JSON)", value=False)

if st.sidebar.button("Clear chat"):
    logger.info("Clearing chat history")
    st.session_state.messages = []
    st.rerun()

# Optional: API health
with st.sidebar.expander("API status", expanded=False):
    try:
        h = requests.get(f"{API_URL}/health", timeout=5)
        logger.debug("Health check response: %s", h.text)
        st.write(h.json())
    except Exception as e:
        logger.error("API health check failed: %s", e, exc_info=True)
        st.error(f"API unreachable: {e}")


# -----------------------------
# Session state
# -----------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []


# -----------------------------
# Replay chat history
# -----------------------------
for m in st.session_state.messages:
    render_message(m, show_sql=show_sql, show_rows=show_rows)


# -----------------------------
# Main loop
# -----------------------------
question = st.chat_input("Ask about clients, invoices, line items...")

if not question:
    logger.debug("No question entered; stopping render")
    st.stop()

# Store + render user message
st.session_state.messages.append({"role": "user", "content": question})
logger.info("User question submitted")
with st.chat_message("user"):
    st.markdown(question)

# Call backend
try:
    data = api_post_chat(API_URL, question)
    logger.info("Backend responded: action=%s", data.get("action"))
except Exception as e:
    logger.error("Backend request failed: %s", e, exc_info=True)
    msg = f"Backend error: {e}"
    with st.chat_message("assistant"):
        st.error(msg)
    append_assistant(msg, mode="error")
    st.stop()

action = data.get("action")

if action == "REFUSE":
    msg = data.get("refusal_message") or (
        "I can only answer questions about the business tables: clients, invoices, and invoice line items."
    )
    logger.warning("Request refused: %s", msg)
    with st.chat_message("assistant"):
        st.warning(msg)
    append_assistant(msg, mode="refuse")
    st.stop()

if action == "CLARIFY":
    msg = data.get("clarifying_question") or "I need one detail to answer. Can you clarify?"
    logger.info("Clarification requested: %s", msg)
    with st.chat_message("assistant"):
        st.info(msg)
    append_assistant(msg, mode="clarify")
    st.stop()

# QUERY
mode = data.get("mode") or "unknown"
narrative = data.get("narrative") or ""
rows = data.get("rows") or []
sql = data.get("sql") or ""
params = data.get("params") or {}

table_md = rows_to_markdown_table(rows) if rows else ""
logger.info("Query response rendered: mode=%s rows=%s", mode, len(rows) if rows else 0)

sql_block = ""
if sql:
    sql_block = f"{sql}\n-- params: {params}"

with st.chat_message("assistant"):
    st.caption(f"Mode: {mode}")
    st.markdown(narrative if narrative else "(no narrative)")
    if table_md:
        st.markdown(table_md)

    if show_sql and sql_block:
        st.code(sql_block, language="sql")
    if show_rows and rows:
        st.json(rows)

append_assistant(
    narrative if narrative else "(no narrative)",
    mode=mode,
    table_md=table_md,
    sql=sql_block if sql_block else None,
    rows=rows[:50] if rows else None,
    show_sql=show_sql,
    show_rows=show_rows,
)
