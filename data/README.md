# FinSight AI sample datasets

These files are small, synthetic datasets for local development and demos.
All amounts are in Indian rupees (INR), and all dates are in ISO format.

- `transactions_sample.csv` can be uploaded through the transaction import endpoint.
- `budgets_sample.json` contains payloads for creating budgets through the API.
- `goals_sample.json` contains payloads for creating financial goals through the API.
- `budget-guide.txt` is a sample knowledge document for the RAG upload endpoint.

The records are fictional and do not contain personal or banking information.

## Insert into MongoDB Atlas

After configuring `backend/.env`, run this from the repository root:

```powershell
python backend/scripts/seed_sample_data.py
```

The command uses `MONGO_USER`, `MONGO_PASSWORD`, `MONGO_CLUSTER`, and
`DATABASE_NAME` from `backend/.env`. It is safe to run again: it replaces only
records created by this sample seed command. Refresh Atlas and open the
configured database's `transactions`, `budgets`, and `financial_goals`
collections.
