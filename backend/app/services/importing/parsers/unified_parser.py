"""
Unified parser module for CSV, Excel (xlsx/xls), PDF, DOCX, and TXT files.
Ensures all formats return a standardized ParsedTable with original row numbers.
"""

from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from app.services.importing.constants import ALLOWED_EXTENSIONS, MAX_FILE_SIZE
from app.services.importing.parsers.models import ParsedRow, ParsedTable


class ParseError(Exception):
    def __init__(self, code: str, message: str, **kwargs: Any):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = kwargs


def sniff_and_validate_file(filename: str, content: bytes) -> str:
    """Validate file extension, size, and content headers."""
    if not filename:
        raise ParseError("INVALID_FILENAME", "Filename is required.")

    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ParseError(
            "UNSUPPORTED_FORMAT",
            f"The file format '{ext}' is not supported.",
            extension=ext,
            filename=filename,
        )

    if len(content) > MAX_FILE_SIZE:
        max_mb = MAX_FILE_SIZE // (1024 * 1024)
        raise ParseError(
            "FILE_TOO_LARGE",
            f"File size exceeds the limit of {max_mb} MB.",
            max_size_mb=max_mb,
            filename=filename,
        )

    if not content or len(content.strip()) == 0:
        raise ParseError(
            "EMPTY_FILE",
            f"The uploaded file '{filename}' is empty.",
            filename=filename,
        )

    # Sniff magic bytes for binary formats
    if ext == ".xlsx" and not content.startswith(b"PK\x03\x04"):
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The file does not appear to be a valid Excel (.xlsx) workbook.",
            filename=filename,
        )
    if ext == ".xls" and not content.startswith(b"\xd0\xcf\x11\xe0"):
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The file does not appear to be a valid legacy Excel (.xls) file.",
            filename=filename,
        )
    if ext == ".docx" and not content.startswith(b"PK\x03\x04"):
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The file does not appear to be a valid Word (.docx) document.",
            filename=filename,
        )
    if ext == ".pdf" and not content.startswith(b"%PDF-"):
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The file does not appear to be a valid PDF document.",
            filename=filename,
        )

    # Check for binary null bytes in CSV/TXT
    if ext in {".csv", ".txt"} and b"\x00" in content[:4096]:
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The text file contains binary data or is corrupted.",
            filename=filename,
        )

    return ext


def parse_csv(filename: str, content: bytes) -> ParsedTable:
    """Parse CSV with UTF-8 BOM detection and fallback encodings."""
    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise ParseError(
            "ENCODING_ERROR",
            f"Unable to decode '{filename}'. Please save the file using UTF-8 encoding.",
            filename=filename,
        )

    # Sniff dialect
    try:
        sample = text[:8192]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect)
    headers: list[str] = []
    rows: list[ParsedRow] = []

    for line_num, raw_row in enumerate(reader, start=1):
        # Strip all cells
        cells = [str(c).strip() if c is not None else "" for c in raw_row]
        if not any(cells):
            continue

        if not headers:
            headers = cells
            continue

        row_dict = {
            headers[i]: cells[i]
            for i in range(min(len(headers), len(cells)))
            if headers[i]
        }
        rows.append(ParsedRow(row_number=line_num, raw_data=row_dict))

    if not headers or not any(headers):
        raise ParseError(
            "EMPTY_FILE",
            f"The CSV file '{filename}' contains no headers.",
            filename=filename,
        )

    return ParsedTable(filename=filename, file_type="csv", headers=headers, rows=rows)


def parse_excel(filename: str, content: bytes, ext: str) -> ParsedTable:
    """Parse Excel files (.xlsx or .xls) selecting the first sheet containing data."""
    if ext == ".xlsx":
        import openpyxl

        try:
            wb = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ParseError(
                "CORRUPT_FILE",
                f"Unable to read '{filename}'. The Excel file is corrupted.",
                filename=filename,
            ) from exc

        try:
            target_sheet_name: str | None = None
            headers: list[str] = []
            rows: list[ParsedRow] = []

            for sheet_name in wb.sheetnames:
                ws = wb[sheet_name]
                sheet_rows = list(ws.iter_rows(values_only=True))
                # Find first non-empty row as header
                hdr_idx = -1
                for idx, r in enumerate(sheet_rows):
                    if r and any(c is not None and str(c).strip() for c in r):
                        hdr_idx = idx
                        break

                if hdr_idx != -1:
                    target_sheet_name = sheet_name
                    raw_hdr = sheet_rows[hdr_idx]
                    headers = [str(c).strip() if c is not None else "" for c in raw_hdr]
                    # Data rows
                    for r_idx, r in enumerate(sheet_rows[hdr_idx + 1 :], start=hdr_idx + 2):
                        if not r or not any(c is not None and str(c).strip() for c in r):
                            continue
                        row_dict = {
                            headers[i]: r[i]
                            for i in range(min(len(headers), len(r)))
                            if headers[i]
                        }
                        rows.append(ParsedRow(row_number=r_idx, raw_data=row_dict))
                    break

            if not headers:
                raise ParseError(
                    "EMPTY_FILE",
                    f"The Excel file '{filename}' contains no usable sheets or data.",
                    filename=filename,
                )

            note = (
                f"Used worksheet '{target_sheet_name}' (first sheet with data)."
                if target_sheet_name
                else ""
            )
            return ParsedTable(
                filename=filename,
                file_type="xlsx",
                headers=headers,
                rows=rows,
                sheet_name=target_sheet_name,
                notes=[note] if note else [],
            )
        finally:
            wb.close()

    else:
        # Legacy .xls
        import xlrd

        try:
            wb = xlrd.open_workbook(file_contents=content)
        except Exception as exc:
            raise ParseError(
                "CORRUPT_FILE",
                f"Unable to read '{filename}'. The legacy Excel file is corrupted.",
                filename=filename,
            ) from exc

        target_sheet_name = None
        headers = []
        rows = []

        for s_idx in range(wb.nsheets):
            ws = wb.sheet_by_index(s_idx)
            if ws.nrows == 0:
                continue

            # Find header row
            hdr_idx = -1
            for r_idx in range(ws.nrows):
                vals = [ws.cell_value(r_idx, c) for c in range(ws.ncols)]
                if any(str(v).strip() for v in vals):
                    hdr_idx = r_idx
                    headers = [str(v).strip() for v in vals]
                    break

            if hdr_idx != -1:
                target_sheet_name = ws.name
                for r_idx in range(hdr_idx + 1, ws.nrows):
                    vals = [ws.cell_value(r_idx, c) for c in range(ws.ncols)]
                    if not any(str(v).strip() for v in vals):
                        continue
                    row_dict = {
                        headers[i]: vals[i]
                        for i in range(min(len(headers), len(vals)))
                        if headers[i]
                    }
                    rows.append(ParsedRow(row_number=r_idx + 1, raw_data=row_dict))
                break

        if not headers:
            raise ParseError(
                "EMPTY_FILE",
                f"The Excel file '{filename}' contains no usable sheets or data.",
                filename=filename,
            )

        note = (
            f"Used worksheet '{target_sheet_name}' (first sheet with data)."
            if target_sheet_name
            else ""
        )
        return ParsedTable(
            filename=filename,
            file_type="xls",
            headers=headers,
            rows=rows,
            sheet_name=target_sheet_name,
            notes=[note] if note else [],
        )


def parse_pdf(filename: str, content: bytes) -> ParsedTable:
    """Parse tables from PDF using PyMuPDF."""
    import pymupdf

    try:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            if doc.is_encrypted:
                raise ParseError(
                    "PASSWORD_PROTECTED",
                    f"The file '{filename}' is password-protected. Please remove password protection and re-upload.",
                    filename=filename,
                )

            headers: list[str] = []
            rows: list[ParsedRow] = []
            row_counter = 2

            for page in doc:
                tables = page.find_tables()
                for table in tables.tables:
                    extracted = table.extract()
                    if not extracted or len(extracted) < 2:
                        continue
                    if not headers:
                        headers = [str(c).strip() if c is not None else "" for c in extracted[0]]
                    for raw_row in extracted[1:]:
                        if not any(str(c).strip() for c in raw_row if c is not None):
                            continue
                        row_dict = {}
                        for i in range(min(len(headers), len(raw_row))):
                            if not headers[i]:
                                continue
                            val = str(raw_row[i]).strip() if raw_row[i] is not None else ""
                            if headers[i].strip().lower() in ("date", "transaction date"):
                                digits = re.sub(r"\D", "", val)
                                if len(digits) == 8:
                                    val = f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
                            row_dict[headers[i]] = val
                        rows.append(ParsedRow(row_number=row_counter, raw_data=row_dict))
                        row_counter += 1

            if not headers or not rows:
                raise ParseError(
                    "NO_TRANSACTIONS_FOUND",
                    f"No transactions were detected in '{filename}'. Ensure the file contains a table with Date, Description, Amount, Type, and Category columns.",
                    filename=filename,
                )

            return ParsedTable(filename=filename, file_type="pdf", headers=headers, rows=rows)
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The PDF file appears to be corrupted or in an unsupported format.",
            filename=filename,
        ) from exc


def parse_docx(filename: str, content: bytes) -> ParsedTable:
    """Parse tables from Word document (.docx)."""
    import docx

    try:
        doc = docx.Document(BytesIO(content))
        headers: list[str] = []
        rows: list[ParsedRow] = []
        row_counter = 2

        for table in doc.tables:
            if not table.rows or len(table.rows) < 2:
                continue
            if not headers:
                headers = [" ".join(cell.text.split()) for cell in table.rows[0].cells]
            for tr in table.rows[1:]:
                cells = [" ".join(cell.text.split()) for cell in tr.cells]
                if not any(cells):
                    continue
                row_dict = {
                    headers[i]: cells[i]
                    for i in range(min(len(headers), len(cells)))
                    if headers[i]
                }
                rows.append(ParsedRow(row_number=row_counter, raw_data=row_dict))
                row_counter += 1

        if not headers or not rows:
            raise ParseError(
                "NO_TRANSACTIONS_FOUND",
                f"No transactions were detected in '{filename}'. Ensure the file contains a table with Date, Description, Amount, Type, and Category columns.",
                filename=filename,
            )

        return ParsedTable(filename=filename, file_type="docx", headers=headers, rows=rows)
    except ParseError:
        raise
    except Exception as exc:
        raise ParseError(
            "CORRUPT_FILE",
            f"Unable to read '{filename}'. The Word document appears to be corrupted.",
            filename=filename,
        ) from exc


def parse_text(filename: str, content: bytes) -> ParsedTable:
    """Parse delimiter-separated text files (.txt)."""
    text: str | None = None
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise ParseError(
            "ENCODING_ERROR",
            f"Unable to decode '{filename}'. Please save the file using UTF-8 encoding.",
            filename=filename,
        )

    try:
        sample = text[:8192]
        dialect = csv.Sniffer().sniff(sample, delimiters="|,\t;")
    except csv.Error:
        dialect = csv.excel_tab

    reader = csv.reader(io.StringIO(text, newline=""), dialect=dialect)
    headers: list[str] = []
    rows: list[ParsedRow] = []

    for line_num, raw_row in enumerate(reader, start=1):
        cells = [str(c).strip() if c is not None else "" for c in raw_row]
        if not any(cells):
            continue

        if not headers:
            headers = cells
            continue

        row_dict = {
            headers[i]: cells[i]
            for i in range(min(len(headers), len(cells)))
            if headers[i]
        }
        rows.append(ParsedRow(row_number=line_num, raw_data=row_dict))

    if not headers or not rows:
        raise ParseError(
            "NO_TRANSACTIONS_FOUND",
            f"No transactions were detected in '{filename}'. Ensure the file contains a table with Date, Description, Amount, Type, and Category columns.",
            filename=filename,
        )

    return ParsedTable(filename=filename, file_type="txt", headers=headers, rows=rows)


def parse_file_to_table(filename: str, content: bytes) -> ParsedTable:
    """Main entrypoint: sniffs file and extracts unified ParsedTable with original row numbers."""
    ext = sniff_and_validate_file(filename, content)
    if ext == ".csv":
        return parse_csv(filename, content)
    if ext in {".xlsx", ".xls"}:
        return parse_excel(filename, content, ext)
    if ext == ".pdf":
        return parse_pdf(filename, content)
    if ext == ".docx":
        return parse_docx(filename, content)
    if ext == ".txt":
        return parse_text(filename, content)
    raise ParseError("UNSUPPORTED_FORMAT", f"Unsupported extension '{ext}'.", extension=ext)
