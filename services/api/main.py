from __future__ import annotations

import os
import logging
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
from app.utils.logging import setup_logging
setup_logging()
logger = logging.getLogger(__name__)

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
        logger.info("Chat request received")

        route = router.route(q)
        logger.debug("Router decision: action=%s, intent=%s", route.action, getattr(route.plan, "intent", None))

        if route.action == "REFUSE":
            logger.info("Refusing request: %s", route.refusal_message)
            return ChatResponse(
                action="REFUSE",
                refusal_message=route.refusal_message,
            )

        if route.action == "CLARIFY":
            logger.info("Clarifying request: %s", route.clarifying_question)
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
            logger.info("Deterministic SQL planned for intent=%s", plan.intent)
        except Exception:
            mode = "freeform"
            ff = freeform.generate(q)
            sql_text, params = ff.safe_sql, {}
            logger.warning("Falling back to freeform SQL generation")

        # Execute + one repair for freeform
        try:
            logger.info("Executing SQL (%s mode)", mode)
            logger.debug("SQL: %s | params=%s", sql_text, params)
            run = sql_agent.run_sql(sql_text, params)
        except Exception as e:
            if mode == "freeform":
                logger.error("Freeform SQL execution failed: %s", e, exc_info=True)
                ff2 = freeform.repair(q, sql_text, str(e))
                sql_text, params = ff2.safe_sql, {}
                logger.info("Retrying with repaired freeform SQL")
                run = sql_agent.run_sql(sql_text, params)
            else:
                logger.error("SQL execution failed", exc_info=True)
                raise

        narrative = synth.synthesize(q, run.sql, run.rows)
        logger.info("SQL executed successfully: %s rows", len(run.rows))

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
