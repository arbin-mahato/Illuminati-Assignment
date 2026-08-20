"""Public, versioned request and response schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ConversationTurn(BaseModel):
    """A compact, non-authoritative prior turn supplied by the browser.

    The API does not persist this data. It is used only to interpret the current
    request and is deliberately limited before it reaches an LLM prompt.
    """

    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=2_000)
    intent: Optional[str] = Field(default=None, max_length=80)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000, description="Natural-language QSR analytics question.")
    session_id: Optional[str] = Field(default=None, max_length=64, description="Browser-generated identifier for one local conversation.")
    history: List[ConversationTurn] = Field(default_factory=list, description="Recent client-held conversation context for follow-up questions.")


class TraceEventResponse(BaseModel):
    agent: str
    action: str
    detail: str


class ChatResponse(BaseModel):
    question: str
    intent: str
    response_mode: str
    answer: str
    insight: Optional[Dict[str, Any]] = None
    tool_result: Optional[Dict[str, Any]] = None
    investigation_result: Optional[Dict[str, Any]] = None
    trace: List[TraceEventResponse]


class HealthResponse(BaseModel):
    status: str


class DatasetMetadataResponse(BaseModel):
    max_order_date: str
    order_count: int
    store_count: int
