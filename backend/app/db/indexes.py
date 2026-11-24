from app.db.collections import (
    FINANCIAL_GOALS,
    IMPORTS,
    IMPORT_STAGING,
    RAG_DOCUMENTS,
    TRANSACTIONS,
)


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
    await transactions.create_index(
        [("user_id", 1), ("fingerprint", 1)],
        name="transactions_user_fingerprint",
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

    imports = database[IMPORTS]
    await imports.create_index(
        [("user_id", 1), ("raw_file_hash", 1)],
        name="imports_user_raw_hash",
    )
    await imports.create_index(
        [("user_id", 1), ("normalized_content_hash", 1)],
        name="imports_user_norm_hash",
    )

    staging = database[IMPORT_STAGING]
    await staging.create_index(
        [("created_at", 1)],
        expireAfterSeconds=1800,
        name="import_staging_ttl",
    )
    await staging.create_index(
        [("user_id", 1), ("import_token", 1)],
        unique=True,
        name="import_staging_token",
    )
