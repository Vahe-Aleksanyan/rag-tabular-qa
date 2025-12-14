from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.engine import get_engine
from app.llm.openai_client import OpenAIClient
from app.rag.router import Router
from app.rag.sql_agent import SQLAgent
from app.rag.sql_builder import build_sql
from app.rag.freeform_sql import FreeformSQLGenerator
from app.rag.answer_synth import AnswerSynth

from .schemas import ChatRequest, ChatResponse


def create_app() -> FastAPI:
    app = FastAPI(title="Tabular QA API", version="1.0.0")

    # Streamlit runs in a different container => allow local compose origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # safe enough for take-home; tighten if you want
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    engine = get_engine()
    sql_agent = SQLAgent(engine)

    llm = OpenAIClient()
    router = Router(llm)
    synth = AnswerSynth(llm)
    freeform = FreeformSQLGenerator(llm)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/chat", response_model=ChatResponse)
    def chat(req: ChatRequest) -> ChatResponse:
        q = req.question.strip()

        route = router.route(q)

        if route.action == "REFUSE":
            return ChatResponse(
                action="REFUSE",
                refusal_message=route.refusal_message,
            )

        if route.action == "CLARIFY":
            return ChatResponse(
                action="CLARIFY",
                clarifying_question=route.clarifying_question,
                missing_fields=route.missing_fields or [],
            )

        plan = route.plan
        mode = "deterministic"

        # Hybrid selection
        try:
            if plan.intent == "FREEFORM_SQL":
                raise ValueError("FREEFORM_SQL")
            built = build_sql(plan)
            sql_text, params = built.sql, built.params
        except Exception:
            mode = "freeform"
            ff = freeform.generate(q)
            sql_text, params = ff.safe_sql, {}

        # Execute + one repair for freeform
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

        return ChatResponse(
            action="QUERY",
            mode=mode,
            narrative=narrative,
            sql=run.sql,
            params=run.params,
            rows=run.rows[:50],
            row_count=len(run.rows),
        )

    return app


app = create_app()
