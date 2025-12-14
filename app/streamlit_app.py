import os
import streamlit as st

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql

st.set_page_config(page_title="Tabular QA", layout="wide")
st.title("Tabular QA — Chat over Excel→MySQL")

# Sidebar model chooser
st.sidebar.header("LLM")
default_model = os.getenv("OPENAI_MODEL", "gpt-5-mini")
model = st.sidebar.text_input("OpenAI model", value=default_model)
if st.sidebar.button("Apply model"):
    os.environ["OPENAI_MODEL"] = model
    st.sidebar.success(f"Using model: {model}")

show_sql = st.sidebar.checkbox("Show SQL", value=True)
show_rows = st.sidebar.checkbox("Show retrieved rows", value=True)

engine = get_engine()
sql_agent = SQLAgent(engine)
router = Router(OpenAIClient())

if "messages" not in st.session_state:
    st.session_state.messages = []

for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

question = st.chat_input("Ask about clients, invoices, line items...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # 1) Plan
    plan = router.plan(question)

    # 2) Deterministic SQL
    built = build_sql(plan)

    # 3) Execute (safe layer still applies LIMIT etc.)
    result = sql_agent.run_sql(built.sql.replace("\n", " ").strip() ,)  # SQL safety will handle LIMIT
    # NOTE: params are not wired in yet (next step). We'll do it in Phase 3.4.

    # 4) Simple grounded answer (for now)
    answer = f"**Intent:** `{plan.intent}`\n\nReturned **{result.row_count}** rows."

    with st.chat_message("assistant"):
        st.markdown(answer)
        if show_sql:
            st.code(result.sql, language="sql")
        if show_rows:
            st.json(result.rows[:50])

    st.session_state.messages.append({"role": "assistant", "content": answer})
