import os
import streamlit as st

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql
from app.rag.answer_synth import AnswerSynth
from app.utils.formatting import rows_to_markdown_table
from app.rag.freeform_sql import FreeformSQLGenerator


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
freeform = FreeformSQLGenerator(llm)


if "messages" not in st.session_state:
    st.session_state.messages = []
if "plan_cache" not in st.session_state:
    st.session_state.plan_cache = {}

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
            if m.get("mode"):
                st.caption(f"Mode: {m['mode']}")



question = st.chat_input("Ask about clients, invoices, line items...")

if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

        # 1) Plan (cache by normalized question to avoid routing instability)
    key = " ".join(question.strip().lower().split())
    if key in st.session_state.plan_cache:
        plan = st.session_state.plan_cache[key]
    else:
        plan = router.plan(question)
        st.session_state.plan_cache[key] = plan

    # 2) Router stability guard:
    # - If router chose a deterministic intent, ALWAYS use deterministic SQL.
    # - Only use freeform if router explicitly returns FREEFORM_SQL OR deterministic builder doesn't support the intent.
    if plan.intent == "FREEFORM_SQL":
        used_mode = "freeform"
        ff = freeform.generate(question)
        sql_text = ff.safe_sql
        sql_params = {}
    else:
        used_mode = "deterministic"
        try:
            built = build_sql(plan)
            sql_text = built.sql
            sql_params = built.params
        except ValueError:
            # Unsupported deterministic intent => fallback
            used_mode = "freeform"
            ff = freeform.generate(question)
            sql_text = ff.safe_sql
            sql_params = {}


    try:
        if plan.intent == "FREEFORM_SQL":
            raise ValueError("Router chose FREEFORM_SQL")
        built = build_sql(plan)
        sql_text = built.sql
        sql_params = built.params
    except Exception:
        used_mode = "freeform"
        ff = freeform.generate(question)
        sql_text = ff.safe_sql
        sql_params = {}

    # 3) Execute (with one repair attempt in freeform mode)
    try:
        run = sql_agent.run_sql(sql_text, sql_params)
    except Exception as e:
        if used_mode == "freeform":
            ff2 = freeform.repair(question, sql_text or "", str(e))
            sql_text = ff2.safe_sql
            sql_params = {}
            run = sql_agent.run_sql(sql_text, sql_params)
        else:
            raise


    # 4) LLM grounded narrative (no table)
    narrative = synth.synthesize(question, run.sql, run.rows)

    # 5) Render table deterministically (exact numbers)
    table_md = rows_to_markdown_table(run.rows)

    assistant_msg = narrative
    with st.chat_message("assistant"):
        st.caption(f"Mode: {used_mode}")
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
        "mode": used_mode,
    })
