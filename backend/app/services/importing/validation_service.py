"""
Comprehensive validation service for FinSight AI file imports.
Implements shared file-level, header-level, and row-level checks
for all file formats (CSV, Excel, PDF, DOCX, TXT).
"""

from __future__ import annotations

import difflib
import math
from pathlib import Path
import re
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from app.core.config import get_settings
from app.domain.dates import get_date_floor, today_ist
from app.domain.normalization import clean_description, clean_spaces
from app.domain.transaction_types import TRANSACTION_TYPES, TYPE_ALIASES
from app.services.importing.constants import MAX_ROWS
from app.services.importing.import_messages import (
    count_label,
    format_rows,
    group_errors,
    render_message,
)
from app.services.importing.parsers.models import ParsedRow, ParsedTable
from app.services.importing.parsers.unified_parser import (
    ParseError,
    parse_file_to_table,
)

# Canonical required columns
REQUIRED_COLUMNS = ["date", "description", "amount", "type", "category"]

# Header aliases map: maps normalized header alias to canonical column name
HEADER_ALIASES: dict[str, str] = {
    # Date
    "date": "date",
    "transaction_date": "date",
    "transactiondate": "date",
    "tx_date": "date",
    "txn_date": "date",
    "trans_date": "date",
    "booking_date": "date",
    "value_date": "date",
    "posting_date": "date",
    # Description
    "description": "description",
    "desc": "description",
    "narration": "description",
    "details": "description",
    "particulars": "description",
    "memo": "description",
    "notes": "description",
    "note": "description",
    "payee": "description",
    "merchant": "description",
    "title": "description",
    "remark": "description",
    "remarks": "description",
    # Amount
    "amount": "amount",
    "amt": "amount",
    "transaction_amount": "amount",
    "txn_amount": "amount",
    "value": "amount",
    "total": "amount",
    "sum": "amount",
    # Type
    "type": "type",
    "transaction_type": "type",
    "transactiontype": "type",
    "txn_type": "type",
    "trans_type": "type",
    "dr_cr": "type",
    "credit_debit": "type",
    "debit_credit": "type",
    "entry_type": "type",
    # Category
    "category": "category",
    "cat": "category",
    "expense_category": "category",
    "transaction_category": "category",
    "tag": "category",
    "tags": "category",
}

BLANK_STRINGS = frozenset(
    {"", "null", "nan", "-", "none", "n/a", "nil", "undefined", "#n/a", "na"}
)

CURRENCY_REGEX = re.compile(r"[₹$€£,]|\b(?:rs\.?|inr)\b|\s+", re.IGNORECASE)


def normalize_header(header: str) -> str:
    """Normalize a header string: strip BOM, trim, lowercase, replace spaces/hyphens with underscore."""
    clean = header.replace("\ufeff", "").strip().lower()
    clean = re.sub(r"[\s\-]+", "_", clean)
    return clean


def is_blank(value: Any) -> bool:
    """Check if a cell value is considered empty, whitespace, null, or NaN."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in BLANK_STRINGS
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def sanitize_formula_injection(value: str) -> str:
    """Sanitize cells starting with =, +, -, @ to prevent spreadsheet formula injection."""
    if value and value[0] in ("=", "+", "-", "@"):
        return "'" + value
    return value


@dataclass
class ValidationIssue:
    code: str
    message: str
    row: int | None = None
    column: str | None = None
    severity: str = "BLOCKING"  # "BLOCKING" or "WARNING"
    sample_value: Any = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "row": self.row,
            "column": self.column,
            "severity": self.severity,
            "sample_value": str(self.sample_value) if self.sample_value is not None else None,
        }


@dataclass
class ValidationReport:
    status: str  # "ready", "needs_confirmation", "rejected"
    filename: str
    file_type: str
    total_rows: int
    valid_rows: list[dict[str, Any]]
    invalid_rows_count: int
    issues: list[dict[str, Any]]
    grouped_issues: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    notes: list[str]
    sheet_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "filename": self.filename,
            "file_type": self.file_type,
            "total_rows": self.total_rows,
            "valid_rows_count": len(self.valid_rows),
            "invalid_rows_count": self.invalid_rows_count,
            "issues": self.issues,
            "grouped_issues": self.grouped_issues,
            "warnings": self.warnings,
            "notes": self.notes,
            "sheet_name": self.sheet_name,
        }


class ValidationService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def parse_date(self, value: Any, row_num: int) -> tuple[str | None, ValidationIssue | None]:
        """Validate and convert date to ISO YYYY-MM-DD. A missing date is an error."""
        if is_blank(value):
            return None, ValidationIssue(
                code="MISSING_VALUE",
                message=f"Date is empty in row {row_num}.",
                row=row_num,
                column="Date",
            )

        parsed_date: date | None = None

        if isinstance(value, datetime):
            parsed_date = value.date()
        elif isinstance(value, date):
            parsed_date = value
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            # Excel serial number (days since 1899-12-30)
            try:
                parsed_date = (datetime(1899, 12, 30) + timedelta(days=float(value))).date()
            except Exception:
                return None, ValidationIssue(
                    code="INVALID_DATE",
                    message=f"Invalid date format in row {row_num}.",
                    row=row_num,
                    column="Date",
                    sample_value=value,
                )
        elif isinstance(value, str):
            clean_str = value.strip()
            patterns = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y")
            for p in patterns:
                try:
                    parsed_date = datetime.strptime(clean_str, p).date()
                    break
                except ValueError:
                    continue

            if not parsed_date and clean_str.isdigit() and 30000 <= int(clean_str) <= 70000:
                try:
                    parsed_date = (datetime(1899, 12, 30) + timedelta(days=int(clean_str))).date()
                except Exception:
                    pass

            if not parsed_date:
                digits = re.sub(r"\D", "", clean_str)
                if len(digits) == 8 and (clean_str.startswith("19") or clean_str.startswith("20")):
                    try:
                        parsed_date = datetime.strptime(f"{digits[:4]}-{digits[4:6]}-{digits[6:]}", "%Y-%m-%d").date()
                    except ValueError:
                        pass

        if not parsed_date:
            return None, ValidationIssue(
                code="INVALID_DATE",
                message=f"Invalid date format in row {row_num}.",
                row=row_num,
                column="Date",
                sample_value=value,
            )

        # Range checks:
        if parsed_date > today_ist():
            return None, ValidationIssue(
                code="FUTURE_DATE",
                message=f"Date cannot be in the future in row {row_num}.",
                row=row_num,
                column="Date",
                sample_value=parsed_date.isoformat(),
            )

        floor = get_date_floor()
        if parsed_date < floor:
            years = self.settings.transaction_date_floor_years
            return None, ValidationIssue(
                code="DATE_TOO_OLD",
                message=f"Date is older than {years} years in row {row_num}.",
                row=row_num,
                column="Date",
                sample_value=parsed_date.isoformat(),
            )

        return parsed_date.isoformat(), None

    def parse_amount(self, value: Any, row_num: int) -> tuple[float | None, ValidationIssue | None]:
        """Validate amount: numeric, > 0, currency symbols stripped, reasonable decimals."""
        if is_blank(value):
            return None, ValidationIssue(
                code="MISSING_VALUE",
                message=f"Amount is empty in row {row_num}.",
                row=row_num,
                column="Amount",
            )

        if isinstance(value, bool):
            return None, ValidationIssue(
                code="INVALID_AMOUNT",
                message=f"Amount must be a valid number in row {row_num}.",
                row=row_num,
                column="Amount",
                sample_value=value,
            )

        num: float | None = None
        if isinstance(value, (int, float)):
            if math.isnan(value) or math.isinf(value):
                return None, ValidationIssue(
                    code="INVALID_AMOUNT",
                    message=f"Amount must be a valid number in row {row_num}.",
                    row=row_num,
                    column="Amount",
                    sample_value=value,
                )
            num = float(value)
        elif isinstance(value, str):
            clean_str = value.strip()
            # Strip currency symbols and formatting commas
            cleaned = CURRENCY_REGEX.sub("", clean_str)
            if not cleaned or is_blank(cleaned):
                return None, ValidationIssue(
                    code="MISSING_VALUE",
                    message=f"Amount is empty in row {row_num}.",
                    row=row_num,
                    column="Amount",
                )
            if re.match(r"^[-+]?\d*\.?\d+[eE][-+]?\d+$", clean_str):
                return None, ValidationIssue(
                    code="INVALID_AMOUNT",
                    message=f"Scientific notation is not permitted for Amount in row {row_num}.",
                    row=row_num,
                    column="Amount",
                    sample_value=value,
                )
            try:
                num = float(cleaned)
            except ValueError:
                return None, ValidationIssue(
                    code="INVALID_AMOUNT",
                    message=f"Amount must be a valid number in row {row_num}.",
                    row=row_num,
                    column="Amount",
                    sample_value=value,
                )

        if num is None:
            return None, ValidationIssue(
                code="INVALID_AMOUNT",
                message=f"Amount must be a valid number in row {row_num}.",
                row=row_num,
                column="Amount",
                sample_value=value,
            )

        if num <= 0:
            return None, ValidationIssue(
                code="AMOUNT_ZERO_OR_NEGATIVE",
                message=f"Amount must be greater than zero in row {row_num}.",
                row=row_num,
                column="Amount",
                sample_value=num,
            )

        max_limit = self.settings.max_inflow_amount
        if num > max_limit:
            return None, ValidationIssue(
                code="AMOUNT_TOO_LARGE",
                message=f"Amount exceeds maximum limit in row {row_num}.",
                row=row_num,
                column="Amount",
                sample_value=num,
            )

        # Decimal 2-place round
        dec = Decimal(str(num))
        rounded = float(dec.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        return rounded, None

    def parse_type(self, value: Any, row_num: int) -> tuple[str | None, ValidationIssue | None]:
        """Validate transaction type against domain canonical types and aliases."""
        if is_blank(value):
            return None, ValidationIssue(
                code="MISSING_VALUE",
                message=f"Type is empty in row {row_num}.",
                row=row_num,
                column="Type",
            )

        raw_str = str(value).strip().lower()
        canonical = TYPE_ALIASES.get(raw_str)
        if not canonical or canonical not in TRANSACTION_TYPES:
            return None, ValidationIssue(
                code="INVALID_TYPE",
                message=f"Invalid transaction type '{value}' in row {row_num}.",
                row=row_num,
                column="Type",
                sample_value=value,
            )

        return canonical, None

    def parse_category(self, value: Any, row_num: int) -> tuple[str | None, ValidationIssue | None]:
        """Validate category: required, length 2-30 characters, clean spaces, lowercase."""
        if is_blank(value):
            return None, ValidationIssue(
                code="MISSING_VALUE",
                message=f"Category is empty in row {row_num}.",
                row=row_num,
                column="Category",
            )

        cleaned = clean_spaces(str(value)).lower()
        cleaned = sanitize_formula_injection(cleaned)

        min_len = self.settings.category_min_length
        max_len = self.settings.category_max_length
        if len(cleaned) < min_len or len(cleaned) > max_len:
            return None, ValidationIssue(
                code="INVALID_CATEGORY",
                message=f"Category must be between {min_len} and {max_len} characters in row {row_num}.",
                row=row_num,
                column="Category",
                sample_value=value,
            )

        return cleaned, None

    def parse_description(
        self, value: Any, row_num: int
    ) -> tuple[str | None, ValidationIssue | None]:
        """Validate description: required, strip HTML/control chars, max length from config."""
        if is_blank(value):
            return None, ValidationIssue(
                code="DESCRIPTION_REQUIRED",
                message=f"Description is required in row {row_num}.",
                row=row_num,
                column="Description",
            )

        try:
            cleaned = clean_description(str(value))
        except ValueError:
            return None, ValidationIssue(
                code="DESCRIPTION_TOO_LONG",
                message=f"Description exceeds {self.settings.description_max_length} characters in row {row_num}.",
                row=row_num,
                column="Description",
                sample_value=value,
            )
        cleaned = sanitize_formula_injection(cleaned)

        if not cleaned:
            return None, ValidationIssue(
                code="DESCRIPTION_REQUIRED",
                message=f"Description is required in row {row_num}.",
                row=row_num,
                column="Description",
            )

        max_len = self.settings.description_max_length
        if len(cleaned) > max_len:
            return None, ValidationIssue(
                code="DESCRIPTION_TOO_LONG",
                message=f"Description exceeds {max_len} characters in row {row_num}.",
                row=row_num,
                column="Description",
                sample_value=value,
            )

        return cleaned, None

    def validate_file(
        self, filename: str, content: bytes, allow_partial: bool = False
    ) -> ValidationReport:
        """
        End-to-end file parsing and validation.
        Returns a standardized ValidationReport.
        """
        # Step 1: Parse file
        try:
            table: ParsedTable = parse_file_to_table(filename, content)
        except ParseError as exc:
            msg = render_message(
                exc.code,
                filename=filename,
                max_size_mb=exc.details.get("max_size_mb", 5),
                extension=exc.details.get("extension", ""),
            )
            issue = ValidationIssue(code=exc.code, message=msg, severity="BLOCKING")
            return ValidationReport(
                status="rejected",
                filename=filename,
                file_type=Path(filename).suffix.lower(),
                total_rows=0,
                valid_rows=[],
                invalid_rows_count=0,
                issues=[issue.to_dict()],
                grouped_issues=[
                    {
                        "code": exc.code,
                        "column": "",
                        "count": 1,
                        "rows": [],
                        "total_rows_affected": 0,
                        "message": msg,
                    }
                ],
                warnings=[],
                notes=[],
            )

        # Check max rows
        if len(table.rows) > MAX_ROWS:
            msg = render_message(
                "MAX_ROWS_EXCEEDED",
                total_rows=len(table.rows),
                max_rows=MAX_ROWS,
                filename=filename,
            )
            issue = ValidationIssue(code="MAX_ROWS_EXCEEDED", message=msg, severity="BLOCKING")
            return ValidationReport(
                status="rejected",
                filename=filename,
                file_type=table.file_type,
                total_rows=len(table.rows),
                valid_rows=[],
                invalid_rows_count=len(table.rows),
                issues=[issue.to_dict()],
                grouped_issues=[
                    {
                        "code": "MAX_ROWS_EXCEEDED",
                        "column": "",
                        "count": len(table.rows),
                        "rows": [],
                        "total_rows_affected": len(table.rows),
                        "message": msg,
                    }
                ],
                warnings=[],
                notes=table.notes,
                sheet_name=table.sheet_name,
            )

        # Step 2: Validate headers
        col_mapping: dict[str, str] = {}  # canonical -> raw_header
        raw_to_canonical: dict[str, str] = {}  # raw_header -> canonical
        duplicate_headers: list[str] = []
        seen_canonical: set[str] = set()
        seen_raw_normalized: set[str] = set()
        unknown_headers: list[str] = []
        warnings: list[ValidationIssue] = []

        all_aliases_list = list(HEADER_ALIASES.keys())

        for raw_hdr in table.headers:
            if not raw_hdr:
                continue
            norm = normalize_header(raw_hdr)

            # Check duplicate raw headers
            if norm in seen_raw_normalized:
                duplicate_headers.append(raw_hdr)
                continue
            seen_raw_normalized.add(norm)

            # Check alias mapping
            canonical = HEADER_ALIASES.get(norm)
            if canonical:
                if canonical in seen_canonical:
                    duplicate_headers.append(raw_hdr)
                else:
                    seen_canonical.add(canonical)
                    col_mapping[canonical] = raw_hdr
                    raw_to_canonical[raw_hdr] = canonical
            else:
                unknown_headers.append(raw_hdr)
                # Fuzzy matching hint
                matches = difflib.get_close_matches(norm, all_aliases_list, n=1, cutoff=0.7)
                if matches:
                    suggested_canonical = HEADER_ALIASES[matches[0]]
                    hint_msg = render_message(
                        "UNKNOWN_COLUMN_HINT",
                        column=raw_hdr,
                        hint=suggested_canonical.capitalize(),
                    )
                    warnings.append(
                        ValidationIssue(
                            code="UNKNOWN_COLUMN_HINT",
                            message=hint_msg,
                            column=raw_hdr,
                            severity="WARNING",
                        )
                    )

        if duplicate_headers:
            dup_col = duplicate_headers[0]
            msg = render_message("DUPLICATE_HEADER", column=dup_col)
            issue = ValidationIssue(
                code="DUPLICATE_HEADER",
                message=msg,
                column=dup_col,
                severity="BLOCKING",
            )
            return ValidationReport(
                status="rejected",
                filename=filename,
                file_type=table.file_type,
                total_rows=len(table.rows),
                valid_rows=[],
                invalid_rows_count=len(table.rows),
                issues=[issue.to_dict()],
                grouped_issues=[
                    {
                        "code": "DUPLICATE_HEADER",
                        "column": dup_col,
                        "count": len(duplicate_headers),
                        "rows": [],
                        "total_rows_affected": 0,
                        "message": msg,
                    }
                ],
                warnings=[w.to_dict() for w in warnings],
                notes=table.notes,
                sheet_name=table.sheet_name,
            )

        missing_cols = [c.capitalize() for c in REQUIRED_COLUMNS if c not in col_mapping]
        if missing_cols:
            file_cols_str = ", ".join(table.headers) if table.headers else "none"
            missing_str = ", ".join(missing_cols)
            msg = render_message(
                "MISSING_COLUMNS",
                filename=filename,
                missing_count=len(missing_cols),
                col_word="column is" if len(missing_cols) == 1 else "columns are",
                missing_columns=missing_str,
                file_columns=file_cols_str,
            )
            issue = ValidationIssue(
                code="MISSING_COLUMNS",
                message=msg,
                column=missing_str,
                severity="BLOCKING",
            )
            return ValidationReport(
                status="rejected",
                filename=filename,
                file_type=table.file_type,
                total_rows=len(table.rows),
                valid_rows=[],
                invalid_rows_count=len(table.rows),
                issues=[issue.to_dict()],
                grouped_issues=[
                    {
                        "code": "MISSING_COLUMNS",
                        "column": missing_str,
                        "count": len(missing_cols),
                        "rows": [],
                        "total_rows_affected": 0,
                        "message": msg,
                    }
                ],
                warnings=[w.to_dict() for w in warnings],
                notes=table.notes,
                sheet_name=table.sheet_name,
            )

        if unknown_headers:
            warn_msg = render_message("UNKNOWN_COLUMNS", columns=", ".join(unknown_headers))
            warnings.append(
                ValidationIssue(
                    code="UNKNOWN_COLUMNS",
                    message=warn_msg,
                    severity="WARNING",
                )
            )

        # Check if table has 0 data rows (header-only file)
        if not table.rows:
            msg = render_message("NO_TRANSACTIONS_FOUND", filename=filename)
            issue = ValidationIssue(
                code="NO_TRANSACTIONS_FOUND",
                message=msg,
                severity="BLOCKING",
            )
            return ValidationReport(
                status="rejected",
                filename=filename,
                file_type=table.file_type,
                total_rows=0,
                valid_rows=[],
                invalid_rows_count=0,
                issues=[issue.to_dict()],
                grouped_issues=[
                    {
                        "code": "NO_TRANSACTIONS_FOUND",
                        "column": "",
                        "count": 1,
                        "rows": [],
                        "total_rows_affected": 0,
                        "message": msg,
                    }
                ],
                warnings=[w.to_dict() for w in warnings],
                notes=table.notes,
                sheet_name=table.sheet_name,
            )

        # Step 3: Row-level validation
        valid_rows: list[dict[str, Any]] = []
        all_row_issues: list[ValidationIssue] = []
        invalid_rows_count = 0

        date_hdr = col_mapping["date"]
        desc_hdr = col_mapping["description"]
        amt_hdr = col_mapping["amount"]
        type_hdr = col_mapping["type"]
        cat_hdr = col_mapping["category"]

        for parsed_row in table.rows:
            r_num = parsed_row.row_number
            data = parsed_row.raw_data

            # Check if entire row is blank
            row_vals = [data.get(h) for h in (date_hdr, desc_hdr, amt_hdr, type_hdr, cat_hdr)]
            if all(is_blank(v) for v in row_vals):
                continue

            row_has_blocking_error = False

            # Validate each field
            v_date, err_date = self.parse_date(data.get(date_hdr), r_num)
            if err_date:
                all_row_issues.append(err_date)
                row_has_blocking_error = True

            v_desc, err_desc = self.parse_description(data.get(desc_hdr), r_num)
            if err_desc:
                all_row_issues.append(err_desc)
                row_has_blocking_error = True

            v_amt, err_amt = self.parse_amount(data.get(amt_hdr), r_num)
            if err_amt:
                all_row_issues.append(err_amt)
                row_has_blocking_error = True

            v_type, err_type = self.parse_type(data.get(type_hdr), r_num)
            if err_type:
                all_row_issues.append(err_type)
                row_has_blocking_error = True

            v_cat, err_cat = self.parse_category(data.get(cat_hdr), r_num)
            if err_cat:
                all_row_issues.append(err_cat)
                row_has_blocking_error = True

            if row_has_blocking_error:
                invalid_rows_count += 1
            else:
                valid_rows.append(
                    {
                        "row_number": r_num,
                        "date": v_date,
                        "description": v_desc,
                        "amount": v_amt,
                        "transaction_type": v_type,
                        "category": v_cat,
                        "raw_data": data,
                    }
                )

        # Build issue lists
        issue_dicts = [iss.to_dict() for iss in all_row_issues[:200]]
        grouped = group_errors([iss.to_dict() for iss in all_row_issues])
        warning_dicts = [w.to_dict() for w in warnings]

        # Determine overall status
        if invalid_rows_count == 0 and valid_rows:
            status = "ready"
        elif valid_rows and allow_partial:
            status = "ready"
        else:
            status = "rejected"

        return ValidationReport(
            status=status,
            filename=filename,
            file_type=table.file_type,
            total_rows=len(valid_rows) + invalid_rows_count,
            valid_rows=valid_rows,
            invalid_rows_count=invalid_rows_count,
            issues=issue_dicts,
            grouped_issues=grouped,
            warnings=warning_dicts,
            notes=table.notes,
            sheet_name=table.sheet_name,
        )
