from pathlib import Path

import pytest

from app.agents.orchestrator import AnalyticsOrchestrator, QueryRouter, TextModel, _bounded_initial_analysis
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


@pytest.mark.parametrize(
    ("question", "intent", "evidence_term"),
    [
        ("Why did monthly revenue change?", "OVERALL_METRICS", "revenue"),
        ("Why is QuickBite Gurugram 04 leading?", "STORE_RANKINGS", "gurugram"),
        ("Why is Zomato revenue greater than Swiggy?", "CHANNEL_PERFORMANCE", "zomato"),
        ("Why is Veg Burger 5 leading?", "SKU_PERFORMANCE", "burger"),
        ("Why is Hyderabad declining?", "CITY_REVENUE_TRENDS", "hyderabad"),
        ("Why does weekend revenue differ?", "WEEKEND_VS_WEEKDAY", "weekend"),
        ("Why does festive revenue differ?", "FESTIVE_VS_NORMAL", "festive"),
        ("Why is ST012 declining?", "STORE_DECLINE_DIAGNOSIS", "st012"),
    ],
)
def test_evidence_bound_follow_ups_recover_from_a_false_model_rejection(
    question: str,
    intent: str,
    evidence_term: str,
) -> None:
    """Every required dashboard can support a related evidence-based follow-up.

    Groq is still called first. This guards against it treating an observational
    ``why`` question as unsupported solely because the workbook cannot prove a
    causal relationship.
    """
    router = QueryRouter(StubModel({"intent": "UNSUPPORTED"}))
    initial_analysis = _bounded_initial_analysis(
        {"intent": intent, "summary": f"Verified analysis includes {evidence_term}.", "tool_result": {"evidence": evidence_term}}
    )
    assert initial_analysis is not None
    route = router.route(
        question,
        conversation_history=[{"role": "assistant", "content": f"Verified analysis includes {evidence_term}.", "intent": intent}],
        initial_analysis=initial_analysis,
    )
    assert route.intent == intent


def test_context_fallback_does_not_turn_an_unrelated_why_question_into_an_analysis() -> None:
    router = QueryRouter(StubModel({"intent": "UNSUPPORTED"}))
    route = router.route(
        "Why is the sky blue?",
        conversation_history=[{"role": "assistant", "content": "Zomato leads channel revenue.", "intent": "CHANNEL_PERFORMANCE"}],
        initial_analysis={"intent": "CHANNEL_PERFORMANCE", "summary": "Zomato leads channel revenue.", "tool_result": {"channels": ["Zomato", "Swiggy"]}},
    )
    assert route.intent == "UNSUPPORTED"


def test_bounded_initial_analysis_keeps_nested_verified_entity_values() -> None:
    context = _bounded_initial_analysis(
        {
            "intent": "CHANNEL_PERFORMANCE",
            "tool_result": {"channels": [{"channel": "Zomato", "revenue": 3651162.76}]},
        }
    )
    assert context is not None
    assert context["tool_result"]["channels"][0]["channel"] == "Zomato"


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
