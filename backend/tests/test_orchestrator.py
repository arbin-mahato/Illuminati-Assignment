from pathlib import Path

import pytest

from app.agents.orchestrator import AnalyticsOrchestrator, TextModel
from app.data.workbook import QSRDataset


class StubModel:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        return self.response


class CapturingModel(StubModel):
    def __init__(self, response: dict[str, object]) -> None:
        super().__init__(response)
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        self.prompts.append(user_prompt)
        return self.response


class SequentialModel:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = responses
        self.prompts: list[str] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, object]:
        self.prompts.append(user_prompt)
        return self.responses.pop(0)


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


def test_entity_based_follow_up_reuses_the_previous_approved_intent(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset).run(
        "Why is Zomato greater than Swiggy?",
        conversation_history=[
            {"role": "assistant", "content": "Zomato and Swiggy lead channel revenue.", "intent": "CHANNEL_PERFORMANCE"},
        ],
    )
    assert state.route is not None
    assert state.route.intent == "CHANNEL_PERFORMANCE"


def test_groq_can_decline_an_out_of_scope_question_using_session_context(dataset: QSRDataset) -> None:
    model = CapturingModel({"intent": "UNSUPPORTED"})
    state = AnalyticsOrchestrator(dataset, model).run(
        "Who is the MOD?",
        conversation_history=[{"role": "assistant", "content": "Zomato and Swiggy lead channel revenue.", "intent": "CHANNEL_PERFORMANCE"}],
    )
    assert state.route is not None
    assert state.route.intent == "UNSUPPORTED"
    assert '"recent_conversation"' in model.prompts[0]
    assert "Zomato and Swiggy" in model.prompts[0]


def test_narrator_receives_initial_analysis_and_current_verified_evidence(dataset: QSRDataset) -> None:
    model = SequentialModel([
        {"intent": "CHANNEL_PERFORMANCE"},
        {"headline": "Zomato versus Swiggy", "summary": "Verified comparison.", "key_findings": [], "recommended_actions": [], "caveat": "Workbook evidence only."},
    ])
    AnalyticsOrchestrator(dataset, model).run(
        "Why is Zomato greater than Swiggy?",
        conversation_history=[{"role": "assistant", "content": "Zomato and Swiggy lead channel revenue.", "intent": "CHANNEL_PERFORMANCE"}],
        initial_analysis={"question": "How do channels compare?", "intent": "CHANNEL_PERFORMANCE", "summary": "Zomato leads.", "tool_result": {"channels": [{"channel": "Zomato", "revenue": 1.0}]}},
    )
    assert '"initial_analysis"' in model.prompts[1]
    assert '"current_verified_evidence"' in model.prompts[1]
    assert "Zomato leads" in model.prompts[1]


def test_channel_comparison_follow_up_has_a_useful_offline_fallback(dataset: QSRDataset) -> None:
    state = AnalyticsOrchestrator(dataset).run(
        "Why is Zomato greater than Swiggy?",
        conversation_history=[{"role": "assistant", "content": "Zomato and Swiggy lead channel revenue.", "intent": "CHANNEL_PERFORMANCE"}],
    )
    assert "Zomato" in state.answer
    assert "Swiggy" in state.answer
    assert "does not prove a causal reason" in state.insight["caveat"]


def test_blank_question_is_rejected(dataset: QSRDataset) -> None:
    with pytest.raises(ValueError, match="blank"):
        AnalyticsOrchestrator(dataset).run("   ")
