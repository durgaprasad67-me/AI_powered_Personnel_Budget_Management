
import openpyxl
import pymupdf
import pytest
from docx import Document as DocxDocument

from app.services.rag.documents import (
    ScannedPdfError,
    normalize_filename,
    parse_document,
    split_documents,
    stable_document_id,
)


def _write_pdf(path, pages):
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
    path.write_bytes(document.tobytes())
    document.close()
    return path.read_bytes()


def _write_docx(path):
    document = DocxDocument()
    document.add_paragraph("The grocery limit is ₹100.")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Date"
    table.cell(0, 1).text = "Amount"
    table.cell(1, 0).text = "2026-06-12"
    table.cell(1, 1).text = "42.75"
    document.save(path)
    return path.read_bytes()


def _write_xlsx(path):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "June"
    sheet.append(["Date", "Merchant", "Amount"])
    for index in range(8):
        sheet.append([f"2026-06-{index + 1:02d}", f"Fresh Mart {index}", 42.75])
    second = workbook.create_sheet("Limits")
    second.append(["Category", "Limit"])
    second.append(["Groceries", 100])
    workbook.save(path)
    return path.read_bytes()


def test_txt_and_docx_are_parsed_to_normalized_text(tmp_path):
    txt_path = tmp_path / "guide.txt"
    txt_path.write_bytes(b"  Keep   receipts.\r\n\r\nTrack spending. ")
    txt = parse_document(txt_path.name, txt_path.read_bytes())
    assert txt[0].page_content == "Keep receipts.\nTrack spending."
    assert txt[0].metadata["file_type"] == "txt"

    docx_path = tmp_path / "guide.docx"
    docx_bytes = _write_docx(docx_path)
    docx = parse_document(docx_path.name, docx_bytes)
    assert "grocery limit is ₹100" in docx[0].page_content
    assert "Date | Amount" in docx[0].page_content


def test_pdf_is_parsed_per_page_with_one_based_page_metadata(tmp_path):
    pdf_path = tmp_path / "guide.pdf"
    content = _write_pdf(pdf_path, ["Page one rules", "Page two details"])

    pages = parse_document(pdf_path.name, content)

    assert [page.metadata["page"] for page in pages] == [1, 2]
    assert pages[0].page_content == "Page one rules"
    assert pages[1].page_content == "Page two details"


def test_scanned_or_empty_text_pdf_returns_clear_ocr_error(tmp_path):
    pdf_path = tmp_path / "scan.pdf"
    content = _write_pdf(pdf_path, [""])

    with pytest.raises(ScannedPdfError, match="OCR is not enabled"):
        parse_document(pdf_path.name, content)


def test_csv_repeats_header_in_each_row_chunk(tmp_path):
    csv_path = tmp_path / "transactions.csv"
    rows = ["Date,Merchant,Note"]
    rows.extend(
        f"2026-06-{index + 1:02d},Fresh Mart {index},weekly grocery purchase"
        for index in range(12)
    )
    csv_path.write_text("\n".join(rows), encoding="utf-8")

    parsed = parse_document(csv_path.name, csv_path.read_bytes())
    chunks = split_documents(parsed, chunk_size=70, chunk_overlap=8)

    assert len(chunks) > 1
    assert all(chunk.page_content.splitlines()[0] == "Date | Merchant | Note" for chunk in chunks)
    assert all("Fresh Mart" in chunk.page_content for chunk in chunks)


def test_xlsx_parses_each_sheet_and_repeats_header_in_chunks(tmp_path):
    xlsx_path = tmp_path / "transactions.xlsx"
    content = _write_xlsx(xlsx_path)

    parsed = parse_document(xlsx_path.name, content)
    chunks = split_documents(parsed, chunk_size=65, chunk_overlap=8)

    assert {document.metadata["sheet"] for document in parsed} == {"June", "Limits"}
    june_chunks = [chunk for chunk in chunks if chunk.metadata["sheet"] == "June"]
    assert len(june_chunks) > 1
    assert all(
        chunk.page_content.splitlines()[0] == "Date | Merchant | Amount"
        for chunk in june_chunks
    )


def test_normalized_filename_is_stable_for_document_identity():
    assert normalize_filename("Folder/  June Guide.TXT ") == "june guide.txt"
    assert stable_document_id("June Guide.TXT") == stable_document_id("june guide.txt")
