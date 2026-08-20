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


def test_streaming_chat_emits_progress_and_a_final_payload(client: TestClient) -> None:
    response = client.post(
        "/api/chat/stream",
        json={"question": "How does revenue and average order value vary across different channels?"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: progress" in response.text
    assert "event: final" in response.text
    assert "CHANNEL_PERFORMANCE" in response.text


def test_streaming_chat_accepts_recent_session_context(client: TestClient) -> None:
    response = client.post(
        "/api/chat/stream",
        json={
            "question": "Can you explain that in simpler terms?",
            "session_id": "demo-session-123",
            "history": [
                {"role": "user", "content": "How does revenue and average order value vary across different channels?"},
                {"role": "assistant", "content": "Zomato leads channel revenue.", "intent": "CHANNEL_PERFORMANCE"},
            ],
        },
    )
    assert response.status_code == 200
    assert "CHANNEL_PERFORMANCE" in response.text


def test_contextual_question_uses_compact_response_mode_unless_visuals_are_requested(client: TestClient) -> None:
    history = [{"role": "assistant", "content": "Zomato leads channel revenue.", "intent": "CHANNEL_PERFORMANCE"}]
    compact = client.post("/api/chat", json={"question": "Can you explain that in simpler terms?", "history": history})
    visual = client.post("/api/chat", json={"question": "Show that in a chart.", "history": history})
    assert compact.json()["response_mode"] == "follow_up"
    assert compact.json()["insight"]["recommended_actions"] == []
    assert visual.json()["response_mode"] == "dashboard"


def test_unrelated_question_is_declined_even_when_the_session_has_analytics_context(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={
            "question": "Who is the PM of India?",
            "history": [{"role": "assistant", "content": "Revenue was stable.", "intent": "OVERALL_METRICS"}],
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "UNSUPPORTED"
    assert body["tool_result"] is None
    assert "QuickBite dataset" in body["answer"]


def test_dataset_entity_follow_up_is_not_rejected_as_unrelated(client: TestClient) -> None:
    response = client.post(
        "/api/chat",
        json={
            "question": "Why is Zomato greater than Swiggy?",
            "history": [{"role": "assistant", "content": "Zomato and Swiggy lead channel revenue.", "intent": "CHANNEL_PERFORMANCE"}],
        },
    )
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == "CHANNEL_PERFORMANCE"
    assert body["response_mode"] == "follow_up"


def test_streaming_chat_accepts_initial_browser_analysis_context(client: TestClient) -> None:
    response = client.post(
        "/api/chat/stream",
        json={
            "question": "Why is Zomato greater than Swiggy?",
            "history": [{"role": "assistant", "content": "Zomato and Swiggy lead channel revenue.", "intent": "CHANNEL_PERFORMANCE"}],
            "initial_analysis": {"intent": "CHANNEL_PERFORMANCE", "summary": "Zomato leads.", "tool_result": {"channels": [{"channel": "Zomato"}]}},
        },
    )
    assert response.status_code == 200
    assert "CHANNEL_PERFORMANCE" in response.text


@pytest.mark.parametrize(
    ("question", "intent"),
    [
        ("What were the total revenue, orders, and average order value for the last 3 months?", "OVERALL_METRICS"),
        ("Which are the top 5 and bottom 5 stores by revenue?", "STORE_RANKINGS"),
        ("How does revenue and average order value vary across different channels?", "CHANNEL_PERFORMANCE"),
        ("Which are the top 5 SKUs by quantity sold and revenue?", "SKU_PERFORMANCE"),
        ("Which cities have shown a decline in revenue over the last 3 months?", "CITY_REVENUE_TRENDS"),
        ("How does weekend performance compare with weekdays?", "WEEKEND_VS_WEEKDAY"),
        ("How does festive-period performance compare with normal periods?", "FESTIVE_VS_NORMAL"),
        ("Which stores have consistently declined in the last 3 months, and what are the key reasons?", "STORE_DECLINE_DIAGNOSIS"),
    ],
)
def test_every_evaluation_question_returns_a_structured_insight(client: TestClient, question: str, intent: str) -> None:
    response = client.post("/api/chat", json={"question": question})
    body = response.json()
    assert response.status_code == 200
    assert body["intent"] == intent
    assert body["insight"]["headline"]
    assert body["insight"]["summary"]
    assert body["insight"]["caveat"]
