# QSR Insight Studio

An agentic analytics application for QSR business data. It uses plain Python orchestration, deterministic DuckDB analytics, and Groq only for natural-language interpretation and evidence-grounded narration.

## Agent flow

```text
Question → Router Agent → Verified analytics tool → [Decline Investigator] → Insight Agent → Response
```

Every number is computed by a tested analytics tool; the model never writes SQL.

## Local run

The fastest complete setup uses Docker Compose:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API health endpoint is `http://localhost:8000/api/health`.

For local development without Docker, create a Python environment, install `backend/requirements.txt`, then run:

```bash
PYTHONPATH=backend uvicorn app.main:app --reload
npm --prefix frontend run dev
```

Use `.env.example` as a reference; do not commit a `.env` file. Exact evaluation questions work without Groq. Set `GROQ_API_KEY` only when you want structured routing of question variants and model-generated evidence narration.

## Verification

```bash
PYTHONPATH=backend pytest backend/tests -q
npm --prefix frontend run build
```

## Deployment

Deploy the API and web services separately, or run the provided Compose stack on a container host. For production, set `CORS_ALLOWED_ORIGINS` to the exact frontend domain and set `NEXT_PUBLIC_API_BASE_URL` to the public API URL at frontend build time.
