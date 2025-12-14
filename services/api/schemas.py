from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1)
    # optional client-provided context later
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    action: str  # QUERY / CLARIFY / REFUSE
    mode: Optional[str] = None  # deterministic / freeform
    narrative: Optional[str] = None

    # If CLARIFY
    clarifying_question: Optional[str] = None
    missing_fields: List[str] = Field(default_factory=list)

    # If REFUSE
    refusal_message: Optional[str] = None

    # For QUERY success
    sql: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
