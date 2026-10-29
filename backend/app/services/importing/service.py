from pathlib import Path
from typing import Any

from app.core.exceptions import InvalidInputError
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
            "Unsupported file format. Allowed formats: PDF, DOCX, TXT, XLSX, XLS.",
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
        raise InvalidInputError(
            "No transaction records were found in the file."
        )
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
                    len(errors) >= 100
                    and len(validated_transactions) != len(rows)
                ),
            }
        )
    return validated_transactions


async def insert_transactions(
    transactions: list[Any],
    repository: TransactionRepository,
) -> list[str]:
    imported_ids: list[str] = []
    for transaction in transactions:
        document = transaction.model_dump(mode="json")
        inserted = await repository.create(document)
        if inserted is None or inserted.get("id") is None:
            raise RuntimeError("Database helper did not return an inserted ID.")
        imported_ids.append(str(inserted["id"]))
    return imported_ids
