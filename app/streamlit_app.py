import os
import streamlit as st

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql
from app.rag.answer_synth import AnswerSynth
from app.utils.formatting import rows_to_markdown_table

st.set_page_config(page_title="Tabular QA", layout="wide")
st.title("Tabular QA — Chat over Excel→MySQL")

st.sidebar.header("LLM")
default_model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
model = st.sidebar.text_input("OpenAI model", value=default_model)
if st.sidebar.button("Apply model"):
    os.environ["OPENAI_MODEL"] = model
    st.sidebar.success(f"Using model: {model}")

show_sql = st.sidebar.checkbox("Show SQL", value=True)
show_rows = st.sidebar.checkbox("Show retrieved rows (JSON)", value=False)

engine = get_engine()
sql_agent = SQLAgent(engine)
llm = OpenAIClient()
router = Router(llm)
synth = AnswerSynth(llm)

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        if m["role"] == "user":
            st.markdown(m["content"])
        else:
            # assistant payload: always has text, may have table/sql/json
            st.markdown(m["content"])
            if m.get("table_md"):
                st.markdown(m["table_md"])
            if m.get("show_sql") and m.get("sql"):
                st.code(m["sql"], language="sql")
            if m.get("show_rows") and m.get("rows"):
                st.json(m["rows"])


question = st.chat_input("Ask about clients, invoices, line items...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # 1) Plan
    plan = router.plan(question)

    # 2) Build deterministic SQL + params
    built = build_sql(plan)

    # 3) Execute safely (parameterized)
    run = sql_agent.run_sql(built.sql, built.params)

    # 4) LLM grounded narrative (no table)
    narrative = synth.synthesize(question, run.sql, run.rows)

    # 5) Render table deterministically (exact numbers)
    table_md = rows_to_markdown_table(run.rows)

    assistant_msg = narrative
    with st.chat_message("assistant"):
        st.markdown(assistant_msg)
        st.markdown(table_md)

        if show_sql:
            st.code(f"{run.sql}\n-- params: {run.params}", language="sql")
        if show_rows:
            st.json(run.rows[:50])

    st.session_state.messages.append({
        "role": "assistant",
        "content": narrative,
        "table_md": table_md,
        "sql": f"{run.sql}\n-- params: {run.params}",
        "rows": run.rows[:50],
        # store the toggles used at the time of answering (optional)
        "show_sql": show_sql,
        "show_rows": show_rows,
    })
