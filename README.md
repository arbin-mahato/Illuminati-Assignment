# QSR Insight Studio

An agentic analytics application for QSR business data. It uses plain Python orchestration, deterministic DuckDB analytics, and Groq only for natural-language interpretation and evidence-grounded narration.

## Agent flow

```text
Question → Router Agent → Verified analytics tool → [Decline Investigator] → Insight Agent → Response
```

Every number is computed by a tested analytics tool; the model never writes SQL.
