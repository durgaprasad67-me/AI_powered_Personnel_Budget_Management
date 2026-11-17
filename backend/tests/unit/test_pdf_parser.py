from pathlib import Path

from app.services.importing.parsers.pdf_parser import extract_pdf
from app.services.importing.service import validate_rows


def test_extract_pdf_normalizes_split_date_cells():
    pdf_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "Transactions_Unique_PDF.pdf"
    )

    rows = extract_pdf(pdf_path.read_bytes())
    validated = validate_rows(rows)

    assert len(rows) == 20
    assert len(validated) == 20
    assert rows[0]["Date"] == "2026-01-07"
    assert rows[1]["Date"] == "2026-01-21"
