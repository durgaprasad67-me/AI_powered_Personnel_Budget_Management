# FinSight AI

## Overview

FinSight AI is a FastAPI personal-finance platform backed by MongoDB Atlas.
It normalizes and analyzes transactions, budgets, and financial goals, and
uses Gemini plus ChromaDB for financial insights and document retrieval.

## Project layout

```text
backend/app/
├── api/            HTTP routes and dependency wiring
├── core/           configuration and application exceptions
├── db/             MongoDB client, collections, and indexes
├── domain/         pure transaction and categorization logic
├── schemas/        Pydantic request and response models
├── repositories/   database access
├── services/       application workflows
└── integrations/   Gemini and ChromaDB integrations
```

## Setup

From `backend`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Fill in `.env` with MongoDB and Gemini credentials. Never commit `.env`;
`.env.example` is the safe template.

## Run locally

From `backend`:

```powershell
python -m uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Interactive documentation
is available at `/docs`.

## Run with Docker

From the repository root:

```powershell
docker compose -f deployment/docker-compose.yml up
```

The Compose configuration mounts the persistent ChromaDB volume at
`/data/chroma`.

## Tests and lint

From `backend`:

```powershell
python -m pytest -q
python -c "import app.main"
ruff check --select F,I,TID252 .
ruff format --check .
lint-imports
```

## API

Application routes use the `/api/v1` prefix:

- `/api/v1/transactions` — transaction CRUD and filtering
- `/api/v1/budgets` — budget CRUD and progress
- `/api/v1/financial-goals` — financial goals and progress
- `/api/v1/analytics/summary` — monthly analytics
- `/api/v1/ai/spending-insights` — Gemini spending insights
- `/api/v1/ai/extract-transaction` — extract a transaction from text
- `/api/v1/ai/rag/documents` — index a knowledge document
- `/api/v1/ai/rag/ask` — query indexed documents
- `/api/v1/imports` — import transactions from CSV, Excel, PDF, DOCX, or TXT

Health checks are available at `/health` and `/api/v1/health`.

## RAG documents

Upload a supported document to `/api/v1/ai/rag/documents` as multipart form
field `file`. The document is split, embedded with Gemini, and stored in
ChromaDB. Query the indexed knowledge base by posting JSON to
`/api/v1/ai/rag/ask`:

```json
{
  "question": "What does the budget guide recommend?",
  "k": 4
}
```
