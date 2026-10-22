# FinSight AI

AI-Powered Personal Finance & Spending Intelligence Platform.

## Existing code reorganized

This cleaned copy keeps files with actual implementation or configuration, plus the new test and work-log files. Empty files and comment/docstring-only placeholders for unimplemented features were removed.

- `backend/app/main.py` — FastAPI application and lifespan
- `backend/app/core/database.py` — MongoDB Atlas connection
- `backend/app/schemas/transaction.py` — transaction request schemas
- `backend/app/routes/v1/transactions.py` — transaction CRUD and filtering
- `backend/app/routes/v1/health.py` — health endpoint
- `backend/app/routes/v1/dashboard.py` — monthly analytics summary
- `backend/app/routes/v1/api.py` — route registration

## Run locally

From the `backend` folder, ensure your local `.env` file contains `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_CLUSTER`, and optionally `DATABASE_NAME`. Do not commit `.env`.

Install dependencies and run:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

API docs: `http://127.0.0.1:8000/docs`

If your MongoDB password was shared or committed previously, rotate it in MongoDB Atlas.


## Daily work log — 23 October 2026

**Focus:** Start automated testing for the existing backend.

### Added today
- Replaced the placeholder `backend/tests/test_transactions.py` with four automated tests:
  1. The home endpoint returns the expected welcome response.
  2. Transaction creation rejects an amount of zero.
  3. Transaction creation rejects an unsupported transaction type.
  4. The transaction schema accepts a valid transaction.
- Added `pytest` and `httpx` to `backend/requirements.txt`.
- Removed zero-byte files from the delivered archive.
- Excluded `.git/`, `.venv/`, Python cache files, and `backend/.env` from the archive to avoid bundling local environment files or secrets.

### Run today's tests
From the `backend` directory:

```bash
python -m pip install -r requirements.txt
python -m pytest tests/test_transactions.py -v
```

These tests are deliberately limited to application behavior and request validation; they do not verify live MongoDB CRUD operations. Database integration tests should be added separately using a dedicated test database or mocked collection methods.
