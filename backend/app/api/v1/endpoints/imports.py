from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_transaction_repository
from app.repositories.transactions import TransactionRepository
from app.schemas.common import ImportResult
from app.services.importing.constants import MAX_FILE_SIZE
from app.services.importing.service import (
    extract_transactions,
    insert_transactions,
    validate_extension,
    validate_rows,
)

router = APIRouter(
    prefix="/imports",
    tags=["File Imports"],
)


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


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Import transactions from a file",
)
async def import_transactions(
    file: UploadFile = File(...),
    repository: TransactionRepository = Depends(get_transaction_repository),
) -> ImportResult:
    """
    Extract, normalize, validate, and import transactions.
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required.",
        )

    filename = file.filename
    validate_extension(filename)

    try:
        content = await _read_file(file)
        rows = extract_transactions(filename, content)
        validated_transactions = validate_rows(rows)
        imported_ids = await insert_transactions(
            validated_transactions,
            repository,
        )

        return {
            "message": "Transactions imported successfully.",
            "filename": filename,
            "total_records": len(rows),
            "imported_records": len(imported_ids),
            "transactions": imported_ids,
        }

    finally:
        await file.close()