from pathlib import Path

import pytest

from app.agents.orchestrator import AnalyticsOrchestrator, TextModel
from app.data.workbook import QSRDataset


class StubModel:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return self.response


@pytest.fixture(scope="module")
def dataset() -> QSRDataset:
    return QSRDataset(Path(__file__).parents[2] / "data" / "QSR_Agentic_Insights_Dataset.xlsx")


def test_known_question_uses_local_route_without_a_model(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset).run("What were the total revenue, orders, and average order value for the last 3 months?")
    assert state.route is not None
    assert state.route.intent == "OVERALL_METRICS"
    assert state.tool_result is not None
    assert "₹" in state.answer


def test_variant_can_route_through_structured_model(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset, StubModel({"intent": "CHANNEL_PERFORMANCE"})).run("Compare my delivery channels")
    assert state.route is not None
    assert state.route.tool_name == "channel_performance"
    assert state.tool_result is not None


def test_q8_takes_the_investigation_path(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset).run("Which stores have consistently declined and what are the key reasons?")
    assert state.investigation_result is not None
    assert state.investigation_result["declining_store_count"] == 9
    assert [entry.agent for entry in state.trace] == ["router", "investigator", "narrator"]


def test_unsupported_question_returns_a_safe_boundary(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset).run("What is tomorrow's weather?")
    assert state.route is not None
    assert state.route.intent == "UNSUPPORTED"
    assert state.tool_result is None


def test_referential_follow_up_reuses_the_previous_approved_intent(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset).run(
        "Can you explain that in simpler terms?",
        conversation_history=[
            {"role": "user", "content": "How do channels compare?"},
            {"role": "assistant", "content": "Zomato leads channel revenue.", "intent": "CHANNEL_PERFORMANCE"},
        ],
    )
    assert state.route is not None
    assert state.route.intent == "CHANNEL_PERFORMANCE"
    assert state.conversation_history[-1]["intent"] == "CHANNEL_PERFORMANCE"


def test_blank_question_is_rejected(dataset: QSRDataset) -> None:
    with pytest.raises(ValueError, match="blank"):
        AnalyticsOrchestrator(dataset).run("   ")
