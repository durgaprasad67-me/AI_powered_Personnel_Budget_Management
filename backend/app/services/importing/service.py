import logging
from pathlib import Path
from typing import Any

from app.core.exceptions import InvalidInputError
from app.core.user_context import DEFAULT_CURRENT_USER_ID
from app.repositories.transactions import TransactionRepository
from app.services.importing.constants import (
    ALLOWED_EXTENSIONS,
    MAX_ROWS,
)
from app.services.importing.parsers.csv_parser import extract_csv
from app.services.importing.parsers.docx_parser import extract_docx
from app.services.importing.parsers.excel_parser import extract_excel
from app.services.importing.parsers.pdf_parser import extract_pdf
from app.services.importing.parsers.text_parser import extract_text
from app.services.importing.validators import validate_transactions
from app.services.rag.transaction_indexing import sync_transactions_best_effort

logger = logging.getLogger(__name__)


def extract_rows(filename: str, content: bytes) -> list[dict[str, Any]]:
    extension = Path(filename).suffix.lower()
    if extension == ".pdf":
        return extract_pdf(content)
    if extension == ".docx":
        return extract_docx(content)
    if extension == ".txt":
        return extract_text(content)
    if extension == ".csv":
        return extract_csv(content)
    if extension in {".xlsx", ".xls"}:
        return extract_excel(content, extension)
    raise InvalidInputError("Unsupported file format.", status_code=415)


def validate_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise InvalidInputError(
            "This file type is not supported. Please choose a CSV, Excel, PDF, DOCX, or TXT file.",
            status_code=415,
        )
    return extension


def extract_transactions(
    filename: str,
    content: bytes,
) -> list[dict[str, Any]]:
    try:
        rows = extract_rows(filename, content)
    except InvalidInputError:
        raise
    except Exception as exc:
        raise InvalidInputError(
            "Unable to read this file. Check that it is valid "
            "and contains a supported transaction table."
        ) from exc

    if not rows:
        raise InvalidInputError("No transaction records were found in the file.")
    if len(rows) > MAX_ROWS:
        raise InvalidInputError(
            f"A maximum of {MAX_ROWS} transactions can be imported at once.",
            status_code=413,
        )
    return rows


def validate_rows(rows: list[dict[str, Any]]) -> list[Any]:
    validated_transactions, errors = validate_transactions(rows, max_errors=100)
    if errors or len(validated_transactions) != len(rows):
        raise InvalidInputError(
            {
                "message": (
                    "Import cancelled because some transaction records "
                    "contain invalid data. No transactions were inserted."
                ),
                "invalid_rows": errors,
                "error_limit_reached": (
                    len(errors) >= 100 and len(validated_transactions) != len(rows)
                ),
            }
        )
    return validated_transactions


async def insert_transactions(
    transactions: list[Any],
    repository: TransactionRepository,
    *,
    user_id: str = DEFAULT_CURRENT_USER_ID,
    import_id: str | None = None,
    vector_sync=sync_transactions_best_effort,
    status_callback=None,
) -> list[str]:
    imported_ids: list[str] = []
    saved_transactions: list[dict[str, Any]] = []
    for transaction in transactions:
        document = transaction.model_dump(mode="json")
        if import_id:
            document["import_id"] = import_id
        inserted = await repository.create(document, user_id=user_id)
        if inserted is None or inserted.get("id") is None:
            raise RuntimeError("Database helper did not return an inserted ID.")
        imported_ids.append(str(inserted["id"]))
        saved_transactions.append(inserted)

    if status_callback:
        await status_callback("embedding")

    # Mongo is the source of truth. A vector outage leaves these rows pending
    # and must not fail an otherwise successful bulk import.
    sync_ok = True
    sync_err = None
    try:
        if vector_sync:
            sync_ok = await vector_sync(
                saved_transactions,
                user_id=user_id,
                repository=repository,
            )
    except Exception as exc:
        sync_ok = False
        sync_err = exc
        logger.warning(
            "Imported transactions were saved but vector indexing failed",
            extra={"error_type": type(exc).__name__},
        )

    if status_callback:
        if sync_ok is not False and sync_err is None:
            await status_callback("completed")
        else:
            err_msg = str(sync_err) if sync_err else "Vector indexing failed"
            await status_callback("embedding_failed", err_msg)

    return imported_ids
