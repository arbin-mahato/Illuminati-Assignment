# QSR Insight Studio

An agentic analytics application for QSR business data. It uses plain Python orchestration, deterministic DuckDB analytics, and Groq only for natural-language interpretation and evidence-grounded narration.

## Agent flow

```text
Question → Router Agent → Verified analytics tool → [Decline Investigator] → Insight Agent → SSE progress stream → Response
```

Groq is the production agent brain: it creates a structured routing plan and composes the final evidence-grounded business insight. Every number is still computed by a tested analytics tool; the model never writes SQL. A deterministic fallback keeps the eight evaluation questions demonstrable if Groq is unavailable.

## Local run

The fastest complete setup uses Docker Compose:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API health endpoint is `http://localhost:8000/api/health`.

For local development without Docker, create a Python environment, install `backend/requirements.txt`, then run these in separate terminals:

```bash
make api
make web
```

Create a root `.env` by copying `.env.example`; do not commit it. The API automatically loads that file when started with `make api`. Set `GROQ_API_KEY` for the full agentic workflow. The UI uses SSE to show routing, tool execution, investigation, and narration as they occur.

## Verification

```bash
PYTHONPATH=backend pytest backend/tests -q
npm --prefix frontend run build
```

## Deployment

Deploy the API and web services separately, or run the provided Compose stack on a container host. For production, set `CORS_ALLOWED_ORIGINS` to the exact frontend domain and set `NEXT_PUBLIC_API_BASE_URL` to the public API URL at frontend build time.
