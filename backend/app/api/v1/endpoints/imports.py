from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.deps import (
    get_current_user_id,
    get_transaction_repository,
    get_transaction_service,
)
from app.core.exceptions import InvalidInputError
from app.repositories.transactions import TransactionRepository
from app.schemas.common import ImportResult
from app.services.importing.constants import MAX_FILE_SIZE
from app.services.importing.normalizers import map_column_name, unsupported_columns
from app.services.importing.service import (
    extract_transactions,
    insert_transactions,
    validate_extension,
    validate_rows,
)
from app.services.importing.validators import validate_transactions
from app.services.transactions import TransactionService

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
    allow_partial: bool = Form(default=False),
    user_id: str = Depends(get_current_user_id),
    repository: TransactionRepository = Depends(get_transaction_repository),
    transaction_service: TransactionService = Depends(get_transaction_service),
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

    try:
        validate_extension(filename)
        content = await _read_file(file)
        rows = extract_transactions(filename, content)
        missing_required = []
        for row_number, row in enumerate(rows, start=1):
            fields = {
                map_column_name(header)
                for header, value in row.items()
                if value not in (None, "") and map_column_name(header)
            }
            missing = []
            if not ({"amount", "debit", "credit"} & fields):
                missing.append("amount (or debit/credit)")
            if missing:
                missing_required.append({"row": row_number, "columns": missing})

        validation_failed = False
        try:
            validated_transactions = validate_rows(rows)
            errors = []
        except InvalidInputError as exc:
            validation_failed = True
            validated_transactions, errors = validate_transactions(rows, max_errors=100)
            if not allow_partial:
                detail = exc.detail if isinstance(exc.detail, dict) else {
                    "message": str(exc.detail),
                    "invalid_rows": [],
                }
                detail.update({
                    "invalid_rows": errors,
                    "unsupported_columns": unsupported_columns(rows),
                    "valid_records": len(validated_transactions),
                    "total_records": len(rows),
                })
                raise HTTPException(status_code=422, detail=detail) from exc

        ignored_columns = unsupported_columns(rows)
        if errors or missing_required or ignored_columns:
            diagnostics = {
                "message": "Some transaction records need attention before import.",
                "invalid_rows": errors,
                "missing_required": missing_required,
                "unsupported_columns": ignored_columns,
                "valid_records": len(validated_transactions),
                "total_records": len(rows),
            }
            if not allow_partial:
                raise HTTPException(status_code=422, detail=diagnostics)

        if validation_failed and not allow_partial and len(validated_transactions) != len(rows):
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Import cancelled because some records are invalid.",
                    "valid_records": len(validated_transactions),
                    "total_records": len(rows),
                },
            )
        if not validated_transactions:
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "No valid transaction records were found. Nothing was imported.",
                    "valid_records": 0,
                    "total_records": len(rows),
                },
            )
        # Preflight the whole file before writing any rows, so a cash or
        # budget limit does not leave a partially imported batch.
        await transaction_service.validate_import_batch(
            validated_transactions,
            user_id=user_id,
        )
        imported_ids = await insert_transactions(
            validated_transactions,
            repository,
            user_id=user_id,
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
