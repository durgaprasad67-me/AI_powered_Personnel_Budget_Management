from app.db.collections import FINANCIAL_GOALS, RAG_DOCUMENTS, TRANSACTIONS


async def ensure_indexes(database) -> None:
    transactions = database[TRANSACTIONS]
    await transactions.create_index([("date", -1), ("_id", -1)])
    await transactions.create_index([("category", 1), ("date", -1), ("_id", -1)])
    await transactions.create_index(
        [("transaction_type", 1), ("date", -1), ("_id", -1)],
        name="transactions_type_date_id",
    )
    await transactions.create_index(
        [("user_id", 1), ("date", -1), ("_id", -1)],
        name="transactions_user_date_id",
    )

    goals = database[FINANCIAL_GOALS]
    await goals.create_index(
        [("status", 1), ("_id", -1)],
        name="goals_status_id",
    )

    rag_documents = database[RAG_DOCUMENTS]
    await rag_documents.create_index(
        [("user_id", 1), ("normalized_filename", 1)],
        unique=True,
        name="rag_documents_user_filename_unique",
    )
    await rag_documents.create_index(
        [("user_id", 1), ("doc_id", 1)],
        unique=True,
        name="rag_documents_user_doc_unique",
    )
