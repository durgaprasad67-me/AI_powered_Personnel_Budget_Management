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
# Development: reload only when backend application files change.
python -m uvicorn app.main:app --reload --reload-dir app
```

The API is available at `http://127.0.0.1:8000`. Interactive documentation
is available at `/docs`.

For a faster, stable local run when you are not actively editing backend code,
start the server without reload:

```powershell
python -m uvicorn app.main:app
```

The project uses the base Uvicorn package and does not install `watchfiles`.
Reload still works through Uvicorn's built-in polling reloader, while normal
startup does not perform any file watching.

The frontend calls this API; it does not connect to MongoDB directly. The
backend reads and writes MongoDB Atlas using `MONGO_USER`, `MONGO_PASSWORD`,
`MONGO_CLUSTER`, and `DATABASE_NAME` from its environment. For a deployed
frontend, set `window.FINSIGHT_API_URL` to the deployed API base URL
(`https://your-api.example.com/api/v1`) before the page scripts load. The
`http://127.0.0.1:8000/api/v1` default is for local development only.

To view the live dashboard, serve `frontend/html` with a local static server
such as VS Code Live Server on port 5500, then open `dashboard.html`. The
dashboard requests the selected month's data from
`/api/v1/dashboard`; dashboard summaries, charts, transactions, budgets, and
goals are returned by the backend.

The feature pages are available from the shared dashboard sidebar:

- `transactions.html` — transaction CRUD and filtering
- `budgets.html` — budget CRUD
- `goals.html` — financial goal CRUD and progress
- `insights.html` — AI spending insights
- `analytics.html` — charts for the selected month
- `reports.html` — CSV download and printable summary
- `imports.html` — transaction and knowledge-document uploads

The pages use the shared frontend shell in `frontend/css/app.css` and
`frontend/js/app.js`. To serve the complete frontend from the repository's
`frontend` directory, use:

```powershell
cd frontend
python -m http.server 5500
```

Then open `http://127.0.0.1:5500/html/dashboard.html`.

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
- `/api/v1/budgets` — budget CRUD and progress, including category/type limits
  that warn at 50%, 75%, and 100% and reject transactions over the limit
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

### Indexing and source of truth

MongoDB remains the source of truth for transactions and uploaded document
content. Manual transactions, imports, edits, and deletes update Chroma as a
best-effort derived index. A failed transaction embedding leaves the Mongo row
saved with `vector_index_status=pending`; stale vectors are hidden from
retrieval. Uploaded PDF, DOCX, TXT, CSV, and XLSX files are stored in Mongo and
indexed in the same Chroma collection with `source_type=document`; transactions
use `source_type=transaction`. The RAG dependency currently supplies the
existing `default_dashboard_user` identity. Real authentication is not part of
this setup.

Chroma uses cosine distance and records the configured embedding model and
dimension in collection metadata. Stored text uses Gemini's
`RETRIEVAL_DOCUMENT` task and questions use `RETRIEVAL_QUERY`. If the embedding
model or dimension changes, rebuild and repopulate the derived index from
Mongo:

```powershell
cd backend
python scripts/reindex_vectors.py --rebuild
```

`--rebuild` drops the configured Chroma collection and reindexes every stored
user's transactions and documents. Run it once after applying the new
collection settings, and again after any model/dimension change. Before
rebuilding a collection from an older version, re-upload documents that exist
only in Chroma; those chunks cannot be recovered after the collection is
dropped. To repair only missing or stale vectors without dropping the
collection, run `python scripts/reindex_vectors.py`; to process one user's
vectors, add `--user-id <id>`.

Transaction totals, counts, averages, and budget remaining are computed by the
Python analytics path. Gemini phrases retrieved facts; it is not asked to do
arithmetic. Retrieval logs include a request ID, hashed user reference,
collection, top-k, threshold, and candidate IDs/scores/pass status. Raw
questions and chunk text are omitted unless `RAG_DEBUG_CONTEXT=true`; keep that
setting disabled in shared or production environments.

### Gemini and RAG environment settings

Configure a pool with `GEMINI_API_KEY_1`, `GEMINI_API_KEY_2`, and
`GEMINI_API_KEY_3` (numbered values take precedence when present), or set
`GEMINI_API_KEYS` to a comma-separated list. The legacy single
`GEMINI_API_KEY` remains a fallback. Keep real values in `backend/.env` or the
deployment secret store; the checked-in `backend/.env.example` contains
placeholders only. Other settings include `GEMINI_MODEL`,
`GEMINI_EMBEDDING_MODEL`, `GEMINI_EMBEDDING_DIM`,
`GEMINI_EMBEDDING_BATCH_SIZE`, `GEMINI_REQUEST_TIMEOUT_SECONDS`,
`GEMINI_MAX_OUTPUT_TOKENS`, `CHROMA_PERSIST_DIRECTORY`,
`CHROMA_COLLECTION_NAME`, `RAG_TOP_K`, `RAG_MIN_SCORE`, `RAG_CHUNK_SIZE`,
`RAG_CHUNK_OVERLAP`, `RAG_MAX_CHUNKS`, `RAG_CONTEXT_MAX_CHARS`, and
`RAG_DEBUG_CONTEXT`.

### RAG tests

From `backend`, the default pytest configuration excludes live tests. Run the
offline suite with:

```powershell
python -m pytest -m "not live" -q
```

The Gemini smoke test is marked `live` and runs only when explicitly selected.
Provide keys through the process environment (tests do not load `.env`) and run:

```powershell
python -m pytest -m live -q
```
