from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.data.workbook import QSRDataset
from app.main import create_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    dataset = QSRDataset(Path(__file__).parents[2] / "data" / "QSR_Agentic_Insights_Dataset.xlsx")
    with TestClient(create_app(dataset)) as test_client:
        yield test_client


def test_health_endpoint(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_metadata_endpoint(client: TestClient) -> None:
    response = client.get("/api/metadata")
    assert response.status_code == 200
    assert response.json()["order_count"] == 20_000


def test_chat_executes_q1_workflow(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": "What were the total revenue, orders, and average order value for the last 3 months?"})
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "OVERALL_METRICS"
    assert body["tool_result"]["total_orders"] > 0
    assert [event["agent"] for event in body["trace"]] == ["router", "analytics_tool", "narrator"]


def test_chat_executes_q8_workflow(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": "Which stores have consistently declined and what are the key reasons?"})
    body = response.json()
    assert response.status_code == 200
    assert body["investigation_result"]["declining_store_count"] == 9


def test_chat_rejects_blank_question(client: TestClient) -> None:
    response = client.post("/api/chat", json={"question": " "})
    assert response.status_code == 400
