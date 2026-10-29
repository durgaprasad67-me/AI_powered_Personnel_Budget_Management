"""
File import routes for FinSight AI.

Supports importing financial transactions from:
PDF, DOCX, TXT, CSV, XLSX, and XLS files.
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.core.database import insert_with_next_id
from app.routes.v1.imports.constants import (
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
    MAX_ROWS,
)
from app.routes.v1.imports.parsers.csv_parser import extract_csv
from app.routes.v1.imports.parsers.docx_parser import extract_docx
from app.routes.v1.imports.parsers.excel_parser import extract_excel
from app.routes.v1.imports.parsers.pdf_parser import extract_pdf
from app.routes.v1.imports.parsers.text_parser import extract_text
from app.routes.v1.imports.validators import validate_transactions

router = APIRouter(
    prefix="/imports",
    tags=["File Imports"],
)


def extract_rows(filename: str, content: bytes) -> list[dict[str, Any]]:
    """
    Select the appropriate parser based on the file extension.
    """
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

    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Unsupported file format.",
    )


def _validate_extension(filename: str) -> str:
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=(
                "Unsupported file format. "
                "Allowed formats: PDF, DOCX, TXT, CSV, XLSX, XLS."
            ),
        )

    return extension


async def _read_file(file: UploadFile) -> bytes:
    content = await file.read(MAX_FILE_SIZE + 1)

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File size must not exceed {MAX_FILE_SIZE // (1024 * 1024)} MB.",
        )

    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    return content


def _extract_transactions(filename: str, content: bytes) -> list[dict[str, Any]]:
    try:
        rows = extract_rows(filename, content)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Unable to read this file. Check that it is valid "
                "and contains a supported transaction table."
            ),
        ) from exc

    if not rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No transaction records were found in the file.",
        )

    if len(rows) > MAX_ROWS:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"A maximum of {MAX_ROWS} transactions can be imported at once.",
        )

    return rows


def _validate_rows(rows: list[dict[str, Any]]) -> list[Any]:
    validated_transactions, errors = validate_transactions(rows, max_errors=100)

    if errors or len(validated_transactions) != len(rows):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": (
                    "Import cancelled because some transaction "
                    "records contain invalid data. "
                    "No transactions were inserted."
                ),
                "invalid_rows": errors,
                "error_limit_reached": (
                    len(errors) >= 100
                    and len(validated_transactions) != len(rows)
                ),
            },
        )

    return validated_transactions


async def _insert_transactions(transactions: list[Any]) -> list[str]:
    imported_ids: list[str] = []

    for transaction in transactions:
        document = transaction.model_dump(mode="json")
        inserted = await insert_with_next_id(document)

        if isinstance(inserted, dict):
            inserted_id = inserted.get("_id")
            if inserted_id is None:
                raise RuntimeError("Database helper returned a document without an ID.")
        else:
            if inserted is None:
                raise RuntimeError("Database helper did not return an inserted ID.")
            inserted_id = inserted

        imported_ids.append(str(inserted_id))

    return imported_ids


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Import transactions from a file",
)
async def import_transactions(file: UploadFile = File(...)) -> dict[str, Any]:
    """
    Extract, normalize, validate, and import transactions.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    filename = file.filename
    _validate_extension(filename)

    try:
        content = await _read_file(file)
        rows = _extract_transactions(filename, content)
        validated_transactions = _validate_rows(rows)
        imported_ids = await _insert_transactions(validated_transactions)

        return {
            "message": "Transactions imported successfully.",
            "filename": filename,
            "total_records": len(rows),
            "imported_records": len(imported_ids),
            "transactions": imported_ids,
        }

    finally:
        await file.close()