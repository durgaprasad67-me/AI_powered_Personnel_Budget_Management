"""
Unit tests for the file validation service and import messages.
"""

from pathlib import Path
import pytest

from app.services.importing.validation_service import ValidationService
from app.services.importing.import_messages import format_rows, group_errors, render_message

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def validator():
    return ValidationService()


def test_clean_sample_file(validator):
    content = (FIXTURES_DIR / "clean_11_rows.csv").read_bytes()
    report = validator.validate_file("clean_11_rows.csv", content)

    assert report.status == "ready"
    assert report.total_rows == 11
    assert len(report.valid_rows) == 11
    assert report.invalid_rows_count == 0
    assert len(report.issues) == 0

    first = report.valid_rows[0]
    assert first["row_number"] == 2
    assert first["date"] == "2026-01-05"
    assert first["amount"] == 52000.0
    assert first["transaction_type"] == "income"
    assert first["category"] == "salary"


def test_missing_amount_cell(validator):
    content = (FIXTURES_DIR / "missing_amount.csv").read_bytes()
    report = validator.validate_file("missing_amount.csv", content)

    assert report.status == "rejected"
    assert report.invalid_rows_count == 1
    assert len(report.valid_rows) == 2
    assert any(iss["code"] == "MISSING_VALUE" and iss["row"] == 3 and iss["column"] == "Amount" for iss in report.issues)


def test_missing_category_column(validator):
    content = (FIXTURES_DIR / "missing_category_column.csv").read_bytes()
    report = validator.validate_file("missing_category_column.csv", content)

    assert report.status == "rejected"
    assert any(iss["code"] == "MISSING_COLUMNS" for iss in report.issues)
    assert "Category" in report.issues[0]["message"]


def test_bad_type(validator):
    content = (FIXTURES_DIR / "bad_type.csv").read_bytes()
    report = validator.validate_file("bad_type.csv", content)

    assert report.status == "rejected"
    assert any(iss["code"] == "INVALID_TYPE" and iss["row"] == 2 for iss in report.issues)


def test_bad_date(validator):
    content = (FIXTURES_DIR / "bad_date.csv").read_bytes()
    report = validator.validate_file("bad_date.csv", content)

    assert report.status == "rejected"
    assert any(iss["code"] == "INVALID_DATE" and iss["row"] == 2 for iss in report.issues)


def test_empty_file(validator):
    content = (FIXTURES_DIR / "empty.csv").read_bytes()
    report = validator.validate_file("empty.csv", content)

    assert report.status == "rejected"
    assert any(iss["code"] == "EMPTY_FILE" for iss in report.issues)


def test_header_only_file(validator):
    content = (FIXTURES_DIR / "header_only.csv").read_bytes()
    report = validator.validate_file("header_only.csv", content)

    assert report.status == "rejected"
    assert any(iss["code"] == "NO_TRANSACTIONS_FOUND" for iss in report.issues)


def test_duplicate_headers(validator):
    content = (FIXTURES_DIR / "duplicate_headers.csv").read_bytes()
    report = validator.validate_file("duplicate_headers.csv", content)

    assert report.status == "rejected"
    assert any(iss["code"] == "DUPLICATE_HEADER" for iss in report.issues)


def test_formula_injection_sanitization(validator):
    content = (FIXTURES_DIR / "formula_injection.csv").read_bytes()
    report = validator.validate_file("formula_injection.csv", content)

    assert report.status == "ready"
    assert report.valid_rows[0]["description"].startswith("'")


def test_currency_symbol_and_formatting_tolerance(validator):
    csv_text = "Date,Description,Amount,Type,Category\n2026-01-05,Groceries,\"₹1,350.50\",expense,food\n"
    report = validator.validate_file("currency.csv", csv_text.encode("utf-8"))

    assert report.status == "ready"
    assert report.valid_rows[0]["amount"] == 1350.50


def test_case_and_whitespace_insensitivity(validator):
    csv_text = "Date,Description,Amount,Type,Category\n2026-01-05,Salary,5000,\" Income \",\" SALARY \"\n"
    report = validator.validate_file("case.csv", csv_text.encode("utf-8"))

    assert report.status == "ready"
    assert report.valid_rows[0]["transaction_type"] == "income"
    assert report.valid_rows[0]["category"] == "salary"


def test_header_fuzzy_matching_hint(validator):
    csv_text = "Date,Description,Amont,Type,Category\n2026-01-05,Salary,5000,income,salary\n"
    report = validator.validate_file("typo.csv", csv_text.encode("utf-8"))

    assert report.status == "rejected"
    assert any("Did you mean 'Amount'?" in w["message"] for w in report.warnings)


def test_indian_and_excel_dates(validator):
    # Test DD/MM/YYYY and DD-MM-YYYY
    date1, err1 = validator.parse_date("15/04/2026", 2)
    assert err1 is None
    assert date1 == "2026-04-15"

    date2, err2 = validator.parse_date("20-05-2026", 3)
    assert err2 is None
    assert date2 == "2026-05-20"


def test_unsupported_extension_and_content_sniffing(validator):
    report = validator.validate_file("virus.exe", b"MZThis is an exe")
    assert report.status == "rejected"
    assert any(iss["code"] == "UNSUPPORTED_FORMAT" for iss in report.issues)

    # Fake xlsx containing plain text
    report2 = validator.validate_file("fake.xlsx", b"not a zip file")
    assert report2.status == "rejected"
    assert any(iss["code"] == "CORRUPT_FILE" for iss in report2.issues)


def test_amount_zero_or_negative(validator):
    csv_zero = "Date,Description,Amount,Type,Category\n2026-01-05,Salary,0,income,salary\n"
    report_zero = validator.validate_file("zero.csv", csv_zero.encode("utf-8"))
    assert report_zero.status == "rejected"
    assert any(iss["code"] == "AMOUNT_ZERO_OR_NEGATIVE" for iss in report_zero.issues)

    csv_neg = "Date,Description,Amount,Type,Category\n2026-01-05,Salary,-500,income,salary\n"
    report_neg = validator.validate_file("neg.csv", csv_neg.encode("utf-8"))
    assert report_neg.status == "rejected"
    assert any(iss["code"] == "AMOUNT_ZERO_OR_NEGATIVE" for iss in report_neg.issues)


def test_date_future_and_floor(validator):
    csv_future = "Date,Description,Amount,Type,Category\n2099-01-01,Salary,5000,income,salary\n"
    report_future = validator.validate_file("future.csv", csv_future.encode("utf-8"))
    assert report_future.status == "rejected"
    assert any(iss["code"] == "FUTURE_DATE" for iss in report_future.issues)

    csv_old = "Date,Description,Amount,Type,Category\n1990-01-01,Salary,5000,income,salary\n"
    report_old = validator.validate_file("old.csv", csv_old.encode("utf-8"))
    assert report_old.status == "rejected"
    assert any(iss["code"] == "DATE_TOO_OLD" for iss in report_old.issues)


def test_description_length_and_category_length(validator):
    long_desc = "X" * 250
    csv_text = f"Date,Description,Amount,Type,Category\n2026-01-05,{long_desc},5000,income,s\n"
    report = validator.validate_file("limits.csv", csv_text.encode("utf-8"))
    assert report.status == "rejected"
    assert any(iss["code"] == "DESCRIPTION_TOO_LONG" for iss in report.issues)
    assert any(iss["code"] == "INVALID_CATEGORY" for iss in report.issues)


def test_partial_import_policy(validator):
    content = (FIXTURES_DIR / "missing_amount.csv").read_bytes()
    # With allow_partial=False, entire file rejected
    report_strict = validator.validate_file("missing_amount.csv", content, allow_partial=False)
    assert report_strict.status == "rejected"
    assert report_strict.invalid_rows_count == 1
    assert len(report_strict.valid_rows) == 2

    # With allow_partial=True, status is ready to import valid rows
    report_partial = validator.validate_file("missing_amount.csv", content, allow_partial=True)
    assert report_partial.status == "ready"
    assert report_partial.invalid_rows_count == 1
    assert len(report_partial.valid_rows) == 2


def test_text_file_pipe_separated(validator):
    txt_content = (
        "Date | Description | Amount | Type | Category\n"
        "2026-01-05 | Monthly salary | 52000 | income | salary\n"
        "2026-01-11 | Apartment rent | 14500 | expense | housing\n"
    )
    report = validator.validate_file("transactions.txt", txt_content.encode("utf-8"))
    assert report.status == "ready"
    assert len(report.valid_rows) == 2
    assert report.valid_rows[0]["description"] == "Monthly salary"

