# QSR Insight Studio

QSR Insight Studio is an agentic analytics application for a quick-service restaurant business. Ask one of the eight business questions in plain English and receive a clear, evidence-backed answer with charts, tables, metrics, and a visible agent progress stream.

The application is deliberately safe: AI interprets the question and explains verified results, while tested DuckDB tools perform every calculation. The language model never writes or runs SQL.

## What it does

- Answers the eight evaluation questions from the supplied QSR workbook.
- Uses Groq for natural-language routing and business-friendly narration.
- Uses deterministic, tested DuckDB queries for all metrics.
- Shows live Server-Sent Events (SSE) progress while the agents work.
- Renders responses as decision-ready dashboards with Recharts, KPI cards, tables, and drill-down evidence.
- Includes a deterministic fallback for the known evaluation questions when Groq is not configured or unavailable.

## How the agentic flow works

```text
Business question
      |
      v
Router agent (Groq) --------> selects a safe, known analysis intent
      |
      v
Verified analytics tool -----> DuckDB calculates from the workbook
      |
      +----> Decline investigator (only for the store-decline question)
      |
      v
Insight narrator (Groq) -----> turns verified evidence into structured advice
      |
      v
SSE progress stream + Next.js dashboard
```

This is agentic AI in a bounded form: each agent has one clear responsibility, tools are selected from an allow-list, and the source workbook remains the only source of numerical truth.

## Supported business questions

1. What were total revenue, orders, and average order value for the last three months?
2. Which five stores were the top and bottom performers by revenue?
3. How do revenue and average order value compare across sales channels?
4. Which five SKUs lead by quantity sold and by revenue?
5. Which cities show a revenue decline?
6. How do weekends compare with weekdays?
7. How do festive days compare with normal days?
8. Which stores declined consistently, and what evidence may explain the decline?

The app resolves “last three months” from the workbook’s latest date, rather than from today’s date. For this dataset, the period is May through July 2026.

## Technology

| Area               | Choice                                           |
| ------------------ | ------------------------------------------------ |
| Web application    | Next.js 14, React 18, TypeScript                 |
| Data visualisation | Recharts                                         |
| API                | FastAPI and Server-Sent Events                   |
| Analytics engine   | DuckDB, Pandas, OpenPyXL                         |
| AI                 | Groq structured-output calls                     |
| Local containers   | Docker Compose                                   |
| Automated checks   | Pytest, Next.js production build, GitHub Actions |

## Project layout

```text
qsr-insight-studio/
├── backend/
│   ├── app/
│   │   ├── agents/          # Router, narrator, and bounded orchestration
│   │   ├── analytics/       # Dataset-relative period handling
│   │   ├── data/            # Workbook loading and validation
│   │   ├── investigations/  # Q8 decline investigation
│   │   ├── tools/           # Allow-listed DuckDB analysis tools
│   │   └── main.py          # FastAPI application
│   └── tests/               # Unit and API integration tests
├── data/                    # Supplied QSR workbook
├── frontend/
│   └── src/                 # Next.js chat and dashboard UI
├── docker-compose.yml        # Complete local stack
├── Makefile                  # Short local commands
└── .env.example              # Safe configuration template
```

## Metric definitions

| Metric              | Definition                               |
| ------------------- | ---------------------------------------- |
| Revenue             | `SUM(NET_REVENUE)` from billed orders    |
| Orders              | `COUNT(DISTINCT ORDER_ID)`               |
| Average order value | Revenue divided by distinct orders       |
| SKU quantity        | `SUM(QUANTITY)` from order details       |
| SKU revenue         | `SUM(LINE_NET_VALUE)` from order details |

On startup, the API verifies the workbook’s required sheets, non-empty data, unique order IDs, non-negative revenue, and order-detail references before serving analysis.

## Run locally

### Prerequisites

- Python 3.9 or newer
- Node.js 20 or newer
- Docker Desktop (only for the Docker option)
- A Groq API key for the full AI routing and narration experience

### 1. Create local configuration

From the repository root:

```bash
cp .env.example .env
```

Open `.env` and set `GROQ_API_KEY`. Keep this file private: it is ignored by Git and must never be committed.

### Option A: Docker (fastest complete local setup)

Start Docker Desktop, then run:

```bash
docker compose up --build
```

Open `http://localhost:3000`. The API health check is at `http://localhost:8000/api/health`.

Stop the stack with `Ctrl+C`, then use `docker compose down` if you also want to remove the containers.

### Option B: Run without Docker

Install dependencies once:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r backend/requirements.txt
npm --prefix frontend ci
```

Then use two terminals from the repository root. Activate `.venv` in the terminal that runs the API.

```bash
# Terminal 1
make api

# Terminal 2
make web
```

The API automatically reads the root `.env` file. Visit `http://localhost:3000` after both services have started.

## Test and build

From the repository root:

```bash
make test
make build
```

`make test` runs the backend’s unit and API integration tests. `make build` creates a production frontend build. The GitHub Actions workflow runs the same checks for pull requests and changes pushed to `main`.

## API

| Method | Endpoint           | Purpose                                                           |
| ------ | ------------------ | ----------------------------------------------------------------- |
| `GET`  | `/api/health`      | Service and dataset health                                        |
| `GET`  | `/api/metadata`    | Dataset metadata                                                  |
| `POST` | `/api/chat`        | Complete structured answer as JSON                                |
| `POST` | `/api/chat/stream` | Progress events followed by the complete structured answer as SSE |

Example request body:

```json
{ "question": "How does revenue and AOV vary across different channels?" }
```

## Deploy

Deploy the FastAPI service on Render from `backend/Dockerfile` with the repository root as its Docker build context. Deploy the Next.js application on Vercel with `frontend` as its root directory.

Set `GROQ_API_KEY` only in Render. Set `NEXT_PUBLIC_API_BASE_URL` in Vercel to the public Render API URL, and set `CORS_ALLOWED_ORIGINS` in Render to the exact Vercel URL. The complete deployment checklist is provided separately with the submission handover.

## Security notes

- Never commit `.env`, API keys, build output, or `node_modules`.
- Store `GROQ_API_KEY` only in your local `.env` and Render’s encrypted environment-variable settings.
- Restrict `CORS_ALLOWED_ORIGINS` to your exact Vercel domain in production.
- The analytics layer only exposes tested query functions; user input cannot become executable SQL.

## License

This project was created as an assignment submission. Do not redistribute the supplied dataset or secrets without permission.
