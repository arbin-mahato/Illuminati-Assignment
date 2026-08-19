"""Public, versioned request and response schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000, description="Natural-language QSR analytics question.")


class TraceEventResponse(BaseModel):
    agent: str
    action: str
    detail: str


class ChatResponse(BaseModel):
    question: str
    intent: str
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
