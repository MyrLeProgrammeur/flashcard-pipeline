import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from parsers.pdf_parser import parse_pdf  # noqa: E402


def _mock_empty_pdfplumber():
    """A pdfplumber.open() context manager whose pages have no text (a scan)."""
    page = MagicMock()
    page.extract_text.return_value = None
    pdf = MagicMock()
    pdf.pages = [page]
    pdf.__enter__.return_value = pdf
    pdf.__exit__.return_value = False
    return pdf


def test_ocr_sidecar_fallback_when_no_text_layer(tmp_path):
    """A scanned PDF with no extractable text falls back to its `.ocr.md` sidecar."""
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")
    sidecar_path = tmp_path / "scan.ocr.md"
    sidecar_path.write_text("# OCR'd content\nHandwritten notes go here.")

    with patch("pdfplumber.open", return_value=_mock_empty_pdfplumber()):
        result = parse_pdf(pdf_path)

    assert result == "# OCR'd content\nHandwritten notes go here."


def test_no_sidecar_behaves_as_today(tmp_path):
    """Missing sidecar: empty extraction stays empty (no crash, no change)."""
    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%%EOF")

    with patch("pdfplumber.open", return_value=_mock_empty_pdfplumber()):
        result = parse_pdf(pdf_path)

    assert result == ""
