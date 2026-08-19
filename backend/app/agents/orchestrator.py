"""A bounded, inspectable agent workflow for QSR analytics.

The workflow never loops autonomously and never lets an LLM write SQL. Groq is optional:
known evaluation questions route locally with zero LLM tokens, while Groq can classify a
natural-language variant and narrate verified evidence when configured.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Protocol

from dotenv import load_dotenv

from app.data.workbook import QSRDataset
from app.investigations.declining_stores import investigate_all_declining_stores
from app.tools.analytics_tools import TOOL_REGISTRY


class TextModel(Protocol):
    """The small model interface needed by the router and narrator."""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]: ...


class GroqTextModel:
    """Groq adapter, created only when a real API key is supplied."""

    def __init__(self, api_key: str, model: str) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Groq returned an empty response")
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("Groq returned a non-object JSON response")
        return parsed


@dataclass(frozen=True)
class Route:
    intent: str
    tool_name: str | None
    requires_investigation: bool = False


@dataclass
class AgentTraceEvent:
    agent: str
    action: str
    detail: str


@dataclass
class AnalysisState:
    question: str
    route: Route | None = None
    tool_result: dict[str, Any] | None = None
    investigation_result: dict[str, Any] | None = None
    answer: str | None = None
    trace: list[AgentTraceEvent] = field(default_factory=list)


class QueryRouter:
    """Select a single approved analytics capability from a business question."""

    _local_routes: tuple[tuple[str, Route], ...] = (
        ("consistently declined", Route("STORE_DECLINE_DIAGNOSIS", None, True)),
        ("key reasons", Route("STORE_DECLINE_DIAGNOSIS", None, True)),
        ("top 5 and bottom 5 stores", Route("STORE_RANKINGS", "store_rankings")),
        ("top 5 skus", Route("SKU_PERFORMANCE", "sku_performance")),
        ("cities have shown a decline", Route("CITY_REVENUE_TRENDS", "city_revenue_trends")),
        ("weekend performance", Route("WEEKEND_VS_WEEKDAY", "weekend_vs_weekday")),
        ("festive-period performance", Route("FESTIVE_VS_NORMAL", "festive_vs_normal")),
        ("different channels", Route("CHANNEL_PERFORMANCE", "channel_performance")),
        ("total revenue, orders", Route("OVERALL_METRICS", "overall_metrics")),
    )
    _routes_by_intent = {
        "OVERALL_METRICS": Route("OVERALL_METRICS", "overall_metrics"),
        "STORE_RANKINGS": Route("STORE_RANKINGS", "store_rankings"),
        "CHANNEL_PERFORMANCE": Route("CHANNEL_PERFORMANCE", "channel_performance"),
        "SKU_PERFORMANCE": Route("SKU_PERFORMANCE", "sku_performance"),
        "CITY_REVENUE_TRENDS": Route("CITY_REVENUE_TRENDS", "city_revenue_trends"),
        "WEEKEND_VS_WEEKDAY": Route("WEEKEND_VS_WEEKDAY", "weekend_vs_weekday"),
        "FESTIVE_VS_NORMAL": Route("FESTIVE_VS_NORMAL", "festive_vs_normal"),
        "STORE_DECLINE_DIAGNOSIS": Route("STORE_DECLINE_DIAGNOSIS", None, True),
    }

    def __init__(self, model: TextModel | None = None) -> None:
        self._model = model

    def route(self, question: str) -> Route:
        local_route = self._local_route(question)
        if self._model is None:
            return local_route or Route("UNSUPPORTED", None)

        # A configured model plans every request. Local matching is only a validated
        # contingency path when the model is unavailable or returns an unsupported plan.
        try:
            response = self._model.complete_json(
                system_prompt=(
                    "You are the routing agent for a QSR analytics application. Return JSON only: "
                    '{"intent":"one allowed intent"}. Allowed intents: ' + ", ".join(self._routes_by_intent)
                ),
                user_prompt=question,
            )
            intent = response.get("intent")
            model_route = self._routes_by_intent.get(intent)
            if model_route:
                return model_route
        except Exception:
            pass
        return local_route or Route("UNSUPPORTED", None)

    def _local_route(self, question: str) -> Route | None:
        normalized = question.casefold()
        for phrase, route in self._local_routes:
            if phrase in normalized:
                return route
        return None


class InsightNarrator:
    """Turn verified output into a compact business answer without changing any figures."""

    def __init__(self, model: TextModel | None = None) -> None:
        self._model = model

    def narrate(self, state: AnalysisState) -> str:
        evidence = state.investigation_result or state.tool_result or {}
        fallback = _deterministic_summary(state.route, evidence)
        if self._model is None:
            return fallback
        try:
            response = self._model.complete_json(
                system_prompt=(
                    "Write one concise QSR executive insight in JSON: {\"answer\": \"...\"}. "
                    "Use only the provided verified evidence. Do not calculate new numbers, invent facts, "
                    "or claim causation from correlation. Limit the answer to 55 words. State only the "
                    "most decision-relevant pattern; detailed rankings and metrics are rendered separately."
                ),
                user_prompt=json.dumps({"question": state.question, "evidence": evidence}, default=str),
            )
            answer = response.get("answer")
            return answer if isinstance(answer, str) and answer.strip() else fallback
        except Exception:
            return fallback


class AnalyticsOrchestrator:
    """Run the bounded Router → Tool → [Investigator] → Narrator workflow."""

    def __init__(self, dataset: QSRDataset, model: TextModel | None = None) -> None:
        self._dataset = dataset
        self._router = QueryRouter(model)
        self._narrator = InsightNarrator(model)

    @classmethod
    def from_environment(cls, dataset: QSRDataset) -> "AnalyticsOrchestrator":
        load_dotenv(Path(__file__).resolve().parents[3] / ".env")
        api_key = os.getenv("GROQ_API_KEY")
        model_name = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
        model = GroqTextModel(api_key, model_name) if api_key else None
        return cls(dataset, model)

    def run(self, question: str) -> AnalysisState:
        state = AnalysisState(question=question.strip())
        if not state.question:
            raise ValueError("Question cannot be blank")

        state.route = self._router.route(state.question)
        state.trace.append(AgentTraceEvent("router", "route_question", state.route.intent))
        if state.route.intent == "UNSUPPORTED":
            state.answer = "I can answer QSR questions about revenue, stores, channels, SKUs, calendar performance, and declining stores."
            return state

        if state.route.requires_investigation:
            state.investigation_result = investigate_all_declining_stores(self._dataset)
            state.trace.append(AgentTraceEvent("investigator", "collect_evidence", "Investigated every consistently declining store."))
        elif state.route.tool_name:
            state.tool_result = TOOL_REGISTRY[state.route.tool_name](self._dataset)
            state.trace.append(AgentTraceEvent("analytics_tool", "execute", state.route.tool_name))

        state.answer = self._narrator.narrate(state)
        state.trace.append(AgentTraceEvent("narrator", "compose_insight", "Generated an evidence-grounded answer."))
        return state

    def run_events(self, question: str) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield a small, bounded SSE-friendly event stream for one analysis request."""
        state = AnalysisState(question=question.strip())
        if not state.question:
            raise ValueError("Question cannot be blank")

        yield "progress", {"agent": "router", "status": "working", "detail": "Interpreting the business question."}
        state.route = self._router.route(state.question)
        state.trace.append(AgentTraceEvent("router", "route_question", state.route.intent))
        yield "progress", {"agent": "router", "status": "complete", "detail": f"Selected {state.route.intent}."}
        if state.route.intent == "UNSUPPORTED":
            state.answer = "I can answer QSR questions about revenue, stores, channels, SKUs, calendar performance, and declining stores."
            yield "final", _state_payload(state)
            return

        if state.route.requires_investigation:
            yield "progress", {"agent": "investigator", "status": "working", "detail": "Investigating declining stores across operational dimensions."}
            state.investigation_result = investigate_all_declining_stores(self._dataset)
            state.trace.append(AgentTraceEvent("investigator", "collect_evidence", "Investigated every consistently declining store."))
            yield "progress", {"agent": "investigator", "status": "complete", "detail": "Collected store, channel, SKU, and promotion evidence."}
        elif state.route.tool_name:
            yield "progress", {"agent": "analytics_tool", "status": "working", "detail": f"Running verified {state.route.tool_name} analysis."}
            state.tool_result = TOOL_REGISTRY[state.route.tool_name](self._dataset)
            state.trace.append(AgentTraceEvent("analytics_tool", "execute", state.route.tool_name))
            yield "progress", {"agent": "analytics_tool", "status": "complete", "detail": "Verified calculations are ready."}

        yield "progress", {"agent": "narrator", "status": "working", "detail": "Composing an evidence-grounded business insight."}
        state.answer = self._narrator.narrate(state)
        state.trace.append(AgentTraceEvent("narrator", "compose_insight", "Generated an evidence-grounded answer."))
        yield "progress", {"agent": "narrator", "status": "complete", "detail": "Insight is ready."}
        yield "final", _state_payload(state)


def _state_payload(state: AnalysisState) -> dict[str, Any]:
    assert state.route is not None
    assert state.answer is not None
    return {
        "question": state.question,
        "intent": state.route.intent,
        "answer": state.answer,
        "tool_result": state.tool_result,
        "investigation_result": state.investigation_result,
        "trace": [event.__dict__ for event in state.trace],
    }


def _deterministic_summary(route: Route | None, evidence: dict[str, Any]) -> str:
    """Provide a reliable offline response, including when a Groq request is unavailable."""
    if route is None:
        return "No analysis route was selected."
    if route.intent == "OVERALL_METRICS":
        return (
            f"From {evidence['period']['start']} to {evidence['period']['end']}, revenue was ₹{evidence['total_revenue']:,.2f} "
            f"from {evidence['total_orders']:,} orders, with an average order value of ₹{evidence['average_order_value']:,.2f}."
        )
    if route.intent == "STORE_RANKINGS":
        return f"Top store: {evidence['top_stores'][0]['store_name']}; lowest-ranked store: {evidence['bottom_stores'][0]['store_name']}."
    if route.intent == "CHANNEL_PERFORMANCE":
        leader = evidence["channels"][0]
        return f"{leader['channel']} is the largest channel, generating ₹{leader['revenue']:,.2f} ({leader['revenue_share_pct']}% of revenue)."
    if route.intent == "SKU_PERFORMANCE":
        quantity_leader = evidence["top_by_quantity"][0]
        revenue_leader = evidence["top_by_revenue"][0]
        return f"Volume leader: {quantity_leader['sku_name']}; revenue leader: {revenue_leader['sku_name']}."
    if route.intent == "CITY_REVENUE_TRENDS":
        cities = evidence["declining_cities"]
        return "Declining cities: " + (", ".join(city["city"] for city in cities) if cities else "none") + "."
    if route.intent == "WEEKEND_VS_WEEKDAY":
        return "Weekend and weekday performance has been calculated using calendar-day normalization."
    if route.intent == "FESTIVE_VS_NORMAL":
        return "Festive and normal-period performance has been calculated using calendar labels."
    if route.intent == "STORE_DECLINE_DIAGNOSIS":
        return (
            f"{evidence['declining_store_count']} stores show a strict three-month revenue decline. "
            "Each store’s order, AOV, channel, SKU, and promotion evidence is included in the analysis."
        )
    return "Analysis completed from verified dataset evidence."
