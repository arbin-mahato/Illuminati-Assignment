"""FastAPI application for QSR Insight Studio."""

from __future__ import annotations

import os
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from app.agents.orchestrator import AnalyticsOrchestrator
from app.api.schemas import ChatRequest, ChatResponse, DatasetMetadataResponse, HealthResponse, TraceEventResponse
from app.data.workbook import QSRDataset, WorkbookValidationError


def create_app(dataset: QSRDataset | None = None, orchestrator: AnalyticsOrchestrator | None = None) -> FastAPI:
    """Construct the application; injection keeps integration tests isolated and deterministic."""
    analytics_dataset = dataset or QSRDataset(_dataset_path())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Fail early in deployment if the dataset was omitted or invalid.
        analytics_dataset.metadata()
        yield

    app = FastAPI(
        title="QSR Insight Studio API",
        version="1.0.0",
        description="Evidence-grounded QSR analytics with a bounded agent workflow.",
        lifespan=lifespan,
    )
    app.state.dataset = analytics_dataset
    # Tests inject a dataset and use the deterministic model-free orchestrator by default.
    # The production module-level application loads Groq credentials from the environment.
    app.state.orchestrator = orchestrator or (
        AnalyticsOrchestrator(analytics_dataset) if dataset is not None else AnalyticsOrchestrator.from_environment(analytics_dataset)
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.api_route("/api/health", methods=["GET", "HEAD"], response_model=HealthResponse, tags=["System"])
    def health() -> HealthResponse:
        """Provide a lightweight health check for browsers and HEAD-based monitors."""
        return HealthResponse(status="ok")

    @app.get("/api/metadata", response_model=DatasetMetadataResponse, tags=["System"])
    def metadata(request: Request) -> DatasetMetadataResponse:
        info = request.app.state.dataset.metadata()
        return DatasetMetadataResponse(**info.__dict__)

    @app.post("/api/chat", response_model=ChatResponse, tags=["Analytics"])
    def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        try:
            state = request.app.state.orchestrator.run(payload.question, _history_payload(payload), payload.initial_analysis)
        except (ValueError, WorkbookValidationError) as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        assert state.route is not None
        assert state.answer is not None
        return ChatResponse(
            question=state.question,
            intent=state.route.intent,
            response_mode=state.response_mode,
            answer=state.answer,
            insight=state.insight,
            tool_result=state.tool_result,
            investigation_result=state.investigation_result,
            trace=[TraceEventResponse(**event.__dict__) for event in state.trace],
        )

    @app.post("/api/chat/stream", tags=["Analytics"])
    def stream_chat(payload: ChatRequest, request: Request) -> StreamingResponse:
        """Stream bounded agent progress and one final structured response over SSE."""
        def event_stream() -> Iterator[str]:
            try:
                for event_name, event_payload in request.app.state.orchestrator.run_events(payload.question, _history_payload(payload), payload.initial_analysis):
                    yield _sse(event_name, event_payload)
            except (ValueError, WorkbookValidationError) as error:
                yield _sse("error", {"detail": str(error)})
            except Exception:
                yield _sse("error", {"detail": "Analysis could not be completed. Please try again."})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _dataset_path() -> Path:
    configured_path = os.getenv("DATASET_PATH")
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return Path(__file__).resolve().parents[2] / "data" / "QSR_Agentic_Insights_Dataset.xlsx"


def _allowed_origins() -> list[str]:
    raw_origins = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw_origins.split(",") if origin.strip()]


def _history_payload(payload: ChatRequest) -> list[dict[str, Any]]:
    """Convert Pydantic models without coupling the orchestrator to HTTP schemas."""
    return [turn.model_dump() for turn in payload.history]


def _sse(event_name: str, payload: dict[str, Any]) -> str:
    return f"event: {event_name}\ndata: {json.dumps(payload, default=str)}\n\n"


app = create_app()
