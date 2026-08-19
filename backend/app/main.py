"""FastAPI application for QSR Insight Studio."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware

from app.agents.orchestrator import AnalyticsOrchestrator
from app.api.schemas import ChatRequest, ChatResponse, DatasetMetadataResponse, HealthResponse, TraceEventResponse
from app.data.workbook import QSRDataset, WorkbookValidationError


def create_app(dataset: QSRDataset | None = None) -> FastAPI:
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
    app.state.orchestrator = AnalyticsOrchestrator.from_environment(analytics_dataset)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/api/health", response_model=HealthResponse, tags=["System"])
    def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @app.get("/api/metadata", response_model=DatasetMetadataResponse, tags=["System"])
    def metadata(request: Request) -> DatasetMetadataResponse:
        info = request.app.state.dataset.metadata()
        return DatasetMetadataResponse(**info.__dict__)

    @app.post("/api/chat", response_model=ChatResponse, tags=["Analytics"])
    def chat(payload: ChatRequest, request: Request) -> ChatResponse:
        try:
            state = request.app.state.orchestrator.run(payload.question)
        except (ValueError, WorkbookValidationError) as error:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
        assert state.route is not None
        assert state.answer is not None
        return ChatResponse(
            question=state.question,
            intent=state.route.intent,
            answer=state.answer,
            tool_result=state.tool_result,
            investigation_result=state.investigation_result,
            trace=[TraceEventResponse(**event.__dict__) for event in state.trace],
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


app = create_app()
