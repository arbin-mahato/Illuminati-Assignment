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
from typing import Any, Iterator, Protocol, Sequence

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
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    response_mode: str = "dashboard"
    initial_analysis: dict[str, Any] | None = None
    route: Route | None = None
    tool_result: dict[str, Any] | None = None
    investigation_result: dict[str, Any] | None = None
    answer: str | None = None
    insight: dict[str, Any] | None = None
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

    def route(
        self,
        question: str,
        conversation_history: Sequence[dict[str, str]] = (),
        initial_analysis: dict[str, Any] | None = None,
    ) -> Route:
        local_route = self._local_route(question)
        context_route = self._context_route(question, conversation_history)
        if self._model is None:
            return local_route or context_route or Route("UNSUPPORTED", None)

        # Groq receives the current question and bounded prior turns, and decides whether
        # the request remains inside the QuickBite dataset scope. Local matching exists
        # only as a no-model or service-failure contingency for the eight required flows.
        try:
            response = self._model.complete_json(
                system_prompt=(
                    "You are the routing agent for a QSR analytics application. Return JSON only: "
                    '{"intent":"one allowed intent or UNSUPPORTED"}. Only choose an intent when the current '
                    "question can be fully answered by one of the approved analyses. Never use a previous "
                    "conversation topic to answer an unrelated question. Return UNSUPPORTED for general knowledge, "
                    "real-world facts, and unsupported dataset requests. Allowed intents: " + ", ".join(self._routes_by_intent)
                ),
                user_prompt=json.dumps(
                    {
                        "question": question,
                        "recent_conversation": conversation_history,
                        "initial_analysis": initial_analysis,
                    },
                    default=str,
                ),
            )
            intent = response.get("intent")
            if intent == "UNSUPPORTED":
                return Route("UNSUPPORTED", None)
            model_route = self._routes_by_intent.get(intent)
            if model_route:
                return model_route
        except Exception:
            pass
        return local_route or context_route or Route("UNSUPPORTED", None)

    def _local_route(self, question: str) -> Route | None:
        normalized = question.casefold()
        for phrase, route in self._local_routes:
            if phrase in normalized:
                return route
        return None

    def _context_route(self, question: str, conversation_history: Sequence[dict[str, str]]) -> Route | None:
        """Keep simple referential follow-ups useful even in offline fallback mode."""
        normalized = question.casefold().strip()
        referential_starts = ("that", "this", "those", "it ", "can you explain", "tell me more", "why did", "show that", "visualize that", "put that")
        if not conversation_history:
            return None
        for turn in reversed(conversation_history):
            if turn.get("role") != "assistant":
                continue
            route = self._routes_by_intent.get(turn.get("intent"))
            if route and (normalized.startswith(referential_starts) or self._references_prior_evidence(normalized, turn.get("content", ""))):
                return route
        return None

    @staticmethod
    def _references_prior_evidence(question: str, prior_answer: str) -> bool:
        """Recognise named entities from the preceding verified response.

        This permits natural follow-ups such as “why is Zomato greater than
        Swiggy?” but not unrelated questions after a prior analytics turn.
        """
        ignored_words = {"about", "across", "after", "before", "could", "does", "from", "have", "into", "more", "than", "that", "their", "there", "these", "this", "through", "which", "while", "with", "would"}
        question_words = {word.strip(".,?!:;()[]{}'\"") for word in question.split()}
        prior_words = {word.strip(".,?!:;()[]{}'\"") for word in prior_answer.casefold().split()}
        comparable_words = {word for word in question_words & prior_words if len(word) >= 4 and word not in ignored_words}
        return bool(comparable_words)

class InsightNarrator:
    """Turn verified output into a compact business answer without changing any figures."""

    def __init__(self, model: TextModel | None = None) -> None:
        self._model = model

    def narrate(self, state: AnalysisState) -> dict[str, Any]:
        evidence = state.investigation_result or state.tool_result or {}
        fallback = _deterministic_insight(state.route, evidence, state.question)
        if state.response_mode == "follow_up":
            fallback["recommended_actions"] = []
        if self._model is None:
            return fallback
        try:
            response = self._model.complete_json(
                system_prompt=(
                    "Return a QSR executive insight as JSON with exactly these fields: "
                    '{"headline":"...","summary":"...","key_findings":["..."],"recommended_actions":["..."],"caveat":"..."}. '
                    "Use only the provided verified evidence. Do not calculate new numbers, invent facts, "
                    "or claim causation from correlation. Keep the summary under 55 words, provide 2–3 useful "
                    "findings and 1–2 practical actions. `current_verified_evidence` is the source of truth. "
                    "Use `initial_analysis` and recent conversation only to understand a follow-up's context; do not "
                    "treat browser-held evidence as more authoritative than the current verified result. Detailed "
                    "rankings and metrics are rendered separately. "
                    + (
                        "This is a follow-up: answer directly, keep recommendations empty, and provide at most two concise findings."
                        if state.response_mode == "follow_up"
                        else ""
                    )
                ),
                user_prompt=json.dumps(
                    {
                        "question": state.question,
                        "recent_conversation": state.conversation_history,
                        "initial_analysis": state.initial_analysis,
                        "current_verified_evidence": evidence,
                    },
                    default=str,
                ),
            )
            insight = _validated_insight(response, fallback)
            if state.response_mode == "follow_up":
                insight["recommended_actions"] = []
            return insight
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

    def run(
        self,
        question: str,
        conversation_history: Sequence[dict[str, Any]] = (),
        initial_analysis: dict[str, Any] | None = None,
    ) -> AnalysisState:
        context = _bounded_history(conversation_history)
        state = AnalysisState(
            question=question.strip(),
            conversation_history=context,
            response_mode=_response_mode(question, context),
            initial_analysis=_bounded_initial_analysis(initial_analysis),
        )
        if not state.question:
            raise ValueError("Question cannot be blank")

        state.route = self._router.route(state.question, state.conversation_history, state.initial_analysis)
        state.trace.append(AgentTraceEvent("router", "route_question", state.route.intent))
        if state.route.intent == "UNSUPPORTED":
            state.insight = _unsupported_insight()
            state.answer = state.insight["summary"]
            return state

        if state.route.requires_investigation:
            state.investigation_result = investigate_all_declining_stores(self._dataset)
            state.trace.append(AgentTraceEvent("investigator", "collect_evidence", "Investigated every consistently declining store."))
        elif state.route.tool_name:
            state.tool_result = TOOL_REGISTRY[state.route.tool_name](self._dataset)
            state.trace.append(AgentTraceEvent("analytics_tool", "execute", state.route.tool_name))

        state.insight = self._narrator.narrate(state)
        state.answer = state.insight["summary"]
        state.trace.append(AgentTraceEvent("narrator", "compose_insight", "Generated an evidence-grounded answer."))
        return state

    def run_events(
        self,
        question: str,
        conversation_history: Sequence[dict[str, Any]] = (),
        initial_analysis: dict[str, Any] | None = None,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield a small, bounded SSE-friendly event stream for one analysis request."""
        context = _bounded_history(conversation_history)
        state = AnalysisState(
            question=question.strip(),
            conversation_history=context,
            response_mode=_response_mode(question, context),
            initial_analysis=_bounded_initial_analysis(initial_analysis),
        )
        if not state.question:
            raise ValueError("Question cannot be blank")

        router_detail = "Reviewing the question and recent session context." if state.conversation_history else "Interpreting the business question."
        yield "progress", {"agent": "router", "status": "working", "detail": router_detail}
        state.route = self._router.route(state.question, state.conversation_history, state.initial_analysis)
        state.trace.append(AgentTraceEvent("router", "route_question", state.route.intent))
        yield "progress", {"agent": "router", "status": "complete", "detail": f"Selected {state.route.intent}."}
        if state.route.intent == "UNSUPPORTED":
            state.insight = _unsupported_insight()
            state.answer = state.insight["summary"]
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
        state.insight = self._narrator.narrate(state)
        state.answer = state.insight["summary"]
        state.trace.append(AgentTraceEvent("narrator", "compose_insight", "Generated an evidence-grounded answer."))
        yield "progress", {"agent": "narrator", "status": "complete", "detail": "Insight is ready."}
        yield "final", _state_payload(state)


def _state_payload(state: AnalysisState) -> dict[str, Any]:
    assert state.route is not None
    assert state.answer is not None
    return {
        "question": state.question,
        "intent": state.route.intent,
        "response_mode": state.response_mode,
        "answer": state.answer,
        "insight": state.insight,
        "tool_result": state.tool_result,
        "investigation_result": state.investigation_result,
        "trace": [event.__dict__ for event in state.trace],
    }


def _bounded_history(history: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    """Limit client-provided context to eight compact turns and six thousand characters.

    Browsers keep the full transcript locally. The model only receives enough recent
    context to resolve follow-ups, keeping requests private and predictable in size.
    """
    compact: list[dict[str, str]] = []
    remaining = 6_000
    for turn in reversed(history[-8:]):
        role = str(turn.get("role", ""))
        content = str(turn.get("content", "")).strip()
        intent = str(turn.get("intent", "")).strip()
        if role not in {"user", "assistant"} or not content:
            continue
        if remaining <= 0:
            break
        trimmed_content = content[:remaining]
        compact.append({"role": role, "content": trimmed_content, "intent": intent})
        remaining -= len(trimmed_content)
    compact.reverse()
    return compact


def _bounded_initial_analysis(analysis: dict[str, Any] | None) -> dict[str, Any] | None:
    """Trim a browser-held first analysis before including it in an LLM request.

    The browser keeps the complete response for the UI. Only a small, structural
    snapshot is returned to the API so follow-up prompts stay fast and predictable.
    It is context only; the fresh DuckDB result remains authoritative.
    """
    if not isinstance(analysis, dict):
        return None

    def trim(value: Any, depth: int = 0) -> Any:
        if isinstance(value, str):
            return value[:800]
        if isinstance(value, (int, float, bool)) or value is None:
            return value
        if depth >= 3:
            return "[omitted for prompt size]"
        if isinstance(value, list):
            return [trim(item, depth + 1) for item in value[:8]]
        if isinstance(value, dict):
            return {str(key)[:80]: trim(item, depth + 1) for key, item in list(value.items())[:12]}
        return str(value)[:800]

    allowed = ("question", "intent", "summary", "tool_result", "investigation_result")
    compact = {key: trim(analysis[key]) for key in allowed if key in analysis}
    if not compact:
        return None
    if len(json.dumps(compact, default=str)) > 12_000:
        return {key: compact[key] for key in ("question", "intent", "summary") if key in compact}
    return compact


def _response_mode(question: str, history: Sequence[dict[str, str]]) -> str:
    """Use a compact chat answer for contextual turns unless visuals are requested."""
    if not history:
        return "dashboard"
    visual_terms = ("chart", "graph", "table", "dashboard", "visual", "breakdown", "plot")
    return "dashboard" if any(term in question.casefold() for term in visual_terms) else "follow_up"


def _unsupported_insight() -> dict[str, Any]:
    return _insight(
        "I can help with the QuickBite dataset",
        "I don’t have information about that outside the QuickBite dataset. Ask me about revenue, stores, channels, SKU demand, calendar performance, or declining stores and I’ll look into it.",
        caveat="This assistant answers only from the supplied QuickBite workbook.",
    )


def _deterministic_insight(route: Route | None, evidence: dict[str, Any], question: str = "") -> dict[str, Any]:
    """Provide a reliable offline response, including when a Groq request is unavailable."""
    if route is None:
        return _insight("Analysis unavailable", "No analysis route was selected.")
    if route.intent == "OVERALL_METRICS":
        return _insight("Three-month performance overview", f"From {evidence['period']['start']} to {evidence['period']['end']}, revenue was ₹{evidence['total_revenue']:,.2f} from {evidence['total_orders']:,} orders, with an average order value of ₹{evidence['average_order_value']:,.2f}.", ["Review the month-by-month trend before setting the next revenue target."], ["Prioritize the month with the strongest order and AOV opportunity."])
    if route.intent == "STORE_RANKINGS":
        return _insight("Store performance ranking", f"{evidence['top_stores'][0]['store_name']} leads revenue, while {evidence['bottom_stores'][0]['store_name']} is the lowest-ranked store in the dataset.", ["Compare the top performer’s channel and product mix with lower-ranked stores."], ["Create a focused recovery plan for the bottom-five stores."])
    if route.intent == "CHANNEL_PERFORMANCE":
        comparison = _channel_comparison_insight(evidence, question)
        if comparison is not None:
            return comparison
        leader = evidence["channels"][0]
        return _insight("Channel performance", f"{leader['channel']} is the largest channel, generating ₹{leader['revenue']:,.2f} and {leader['revenue_share_pct']}% of revenue.", ["Use revenue share and AOV together when comparing channels."], ["Protect the leading channel while testing AOV improvement in lower-value channels."])
    if route.intent == "SKU_PERFORMANCE":
        quantity_leader = evidence["top_by_quantity"][0]
        revenue_leader = evidence["top_by_revenue"][0]
        return _insight("SKU performance", f"{quantity_leader['sku_name']} leads unit volume, while {revenue_leader['sku_name']} generates the most revenue.", ["Volume and revenue leaders are not necessarily the same product."], ["Protect availability of leading SKUs and test attach-rate offers for high-value items."])
    if route.intent == "CITY_REVENUE_TRENDS":
        cities = evidence["declining_cities"]
        city_names = ", ".join(city["city"] for city in cities) if cities else "none"
        return _insight("City revenue trend", f"Cities with a May-to-July revenue decline: {city_names}.", ["The trend is measured from the first to final month, not a causal diagnosis."], ["Review store-level drivers in declining cities before changing local promotions."])
    if route.intent == "WEEKEND_VS_WEEKDAY":
        return _insight("Weekend versus weekday", "Weekend and weekday performance is normalized by calendar day for a fair comparison.", ["Daily revenue prevents a five-day weekday period from dominating the comparison."], ["Use the higher daily-revenue segment to guide staffing and campaign timing."])
    if route.intent == "FESTIVE_VS_NORMAL":
        return _insight("Festive-period performance", "Festive and normal periods are compared using the dataset’s calendar labels and daily revenue normalization.", ["Daily revenue gives a comparable view across periods of different lengths."], ["Use the strongest festive response to plan inventory and channel capacity."])
    if route.intent == "STORE_DECLINE_DIAGNOSIS":
        return _insight("Consistently declining stores", f"{evidence['declining_store_count']} stores show a strict three-month revenue decline. Order, AOV, channel, SKU, and promotion evidence is available for every affected store.", ["The evidence identifies observed contributors, not proven causes."], ["Prioritize the steepest-declining stores for a focused recovery review."], "Driver evidence is correlational and should be validated with store operations.")
    return _insight("Analysis complete", "Analysis completed from verified dataset evidence.")


def _channel_comparison_insight(evidence: dict[str, Any], question: str) -> dict[str, Any] | None:
    """Make the offline fallback useful for direct named-channel follow-ups."""
    mentioned = [
        channel for channel in evidence.get("channels", [])
        if str(channel.get("channel", "")).casefold() in question.casefold()
    ]
    if len(mentioned) != 2:
        return None
    first, second = mentioned
    revenue_gap = first["revenue"] - second["revenue"]
    order_gap = first["orders"] - second["orders"]
    aov_gap = first["average_order_value"] - second["average_order_value"]
    relation = "higher" if revenue_gap >= 0 else "lower"
    return _insight(
        f"{first['channel']} versus {second['channel']}",
        f"{first['channel']} generated ₹{first['revenue']:,.2f}, which is ₹{abs(revenue_gap):,.2f} {relation} than {second['channel']}. The observed revenue gap aligns with {first['orders']:,} versus {second['orders']:,} orders and an AOV of ₹{first['average_order_value']:,.2f} versus ₹{second['average_order_value']:,.2f}.",
        [
            f"Order volume differs by {abs(order_gap):,} orders.",
            f"AOV differs by ₹{abs(aov_gap):,.2f}.",
        ],
        [],
        "The dataset shows the observed revenue, order, and AOV gap; it does not prove a causal reason.",
    )


def _insight(headline: str, summary: str, findings: list[str] | None = None, actions: list[str] | None = None, caveat: str = "All metrics are calculated from the supplied workbook.") -> dict[str, Any]:
    return {"headline": headline, "summary": summary, "key_findings": findings or [], "recommended_actions": actions or [], "caveat": caveat}


def _validated_insight(candidate: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    headline = candidate.get("headline")
    summary = candidate.get("summary")
    if not isinstance(headline, str) or not headline.strip() or not isinstance(summary, str) or not summary.strip():
        return fallback
    return {
        "headline": headline.strip(),
        "summary": summary.strip(),
        "key_findings": [item.strip() for item in candidate.get("key_findings", []) if isinstance(item, str) and item.strip()][:3],
        "recommended_actions": [item.strip() for item in candidate.get("recommended_actions", []) if isinstance(item, str) and item.strip()][:2],
        "caveat": candidate.get("caveat").strip() if isinstance(candidate.get("caveat"), str) and candidate["caveat"].strip() else fallback["caveat"],
    }
