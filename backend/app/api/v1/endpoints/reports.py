import csv
import io
from calendar import monthrange
from datetime import date as Date
from typing import Literal

import pymupdf
from docx import Document
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from app.api.deps import get_transaction_service
from app.services.transactions import TransactionService

router = APIRouter(prefix="/reports", tags=["Reports"])

ExportFormat = Literal["csv", "xlsx", "pdf", "docx", "txt"]
ReportPeriod = Literal["month", "year"]


async def _transactions_for_period(
    service: TransactionService,
    *,
    period: ReportPeriod,
    value: str,
) -> tuple[list[dict], str]:
    if period == "month":
        year, month = (int(part) for part in value.split("-"))
        start = Date(year, month, 1)
        end = Date(year, month, monthrange(year, month)[1])
        label = value
    else:
        year = int(value)
        start = Date(year, 1, 1)
        end = Date(year, 12, 31)
        label = value

    items: list[dict] = []
    skip = 0
    limit = 100
    while True:
        page = await service.list(
            transaction_type=None,
            category=None,
            start_date=start.isoformat(),
            end_date=end.isoformat(),
            limit=limit,
            skip=skip,
        )
        page_items = page["items"]
        items.extend(page_items)
        if not page_items or len(items) >= page["total"]:
            return items, label
        skip += len(page_items)


def _rows(items: list[dict]) -> list[list[str | int | float]]:
    return [
        ["Date", "Description", "Category", "Type", "Amount"],
        *[
            [
                item["date"],
                item["description"],
                item["category"],
                item["transaction_type"],
                item["amount"],
            ]
            for item in items
        ],
    ]


def _create_export(items: list[dict], label: str, file_format: ExportFormat) -> tuple[bytes, str, str]:
    rows = _rows(items)
    filename = f"FinSight_Transactions_{label}.{file_format}"

    if file_format == "csv":
        output = io.StringIO()
        csv.writer(output).writerows(rows)
        return output.getvalue().encode("utf-8-sig"), filename, "text/csv; charset=utf-8"

    if file_format == "txt":
        content = "\n".join("\t".join(str(value) for value in row) for row in rows)
        return content.encode("utf-8"), filename, "text/plain; charset=utf-8"

    if file_format == "xlsx":
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Transactions"
        for row in rows:
            sheet.append(row)
        output = io.BytesIO()
        workbook.save(output)
        return output.getvalue(), filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    if file_format == "docx":
        document = Document()
        document.add_heading(f"FinSight AI Transactions - {label}", level=1)
        table = document.add_table(rows=1, cols=len(rows[0]))
        for cell, value in zip(table.rows[0].cells, rows[0]):
            cell.text = str(value)
        for row in rows[1:]:
            cells = table.add_row().cells
            for cell, value in zip(cells, row):
                cell.text = str(value)
        output = io.BytesIO()
        document.save(output)
        return output.getvalue(), filename, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    document = pymupdf.open()
    page = document.new_page()
    lines = [f"FinSight AI Transactions - {label}", ""]
    lines.extend(" | ".join(str(value) for value in row) for row in rows)
    page.insert_text((40, 50), "\n".join(lines), fontsize=9)
    output = document.tobytes()
    document.close()
    return output, filename, "application/pdf"


@router.get("/transactions")
async def export_transactions(
    period: ReportPeriod = Query(default="month"),
    value: str = Query(..., pattern=r"^(?:\d{4}-(?:0[1-9]|1[0-2])|\d{4})$"),
    file_format: ExportFormat = Query(default="csv", alias="format"),
    service: TransactionService = Depends(get_transaction_service),
):
    if period == "month" and len(value) != 7:
        raise HTTPException(status_code=422, detail="Month value must use YYYY-MM format.")
    if period == "year" and len(value) != 4:
        raise HTTPException(status_code=422, detail="Year value must use YYYY format.")

    items, label = await _transactions_for_period(service, period=period, value=value)
    content, filename, media_type = _create_export(items, label, file_format)
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
