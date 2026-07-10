"""
A scanned PDF (no text layer, no sidecar) must be OCR'd automatically and its
text used — never dropped silently. Cost guards must refuse loudly instead.
"""
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline  # noqa: E402

CFG = {
    "ocr": {
        "enabled": True,
        "provider": "gemini",
        "model": "gemini-3.5-flash",
        "dpi": 200,
        "batch_pages": 20,
        "max_pages": 400,
    }
}


@pytest.fixture
def scan(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF")
    return pdf


def test_scan_is_ocrd_and_sidecar_written(scan, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def fake_ocr(filepath, **kwargs):
        sidecar = filepath.with_name(filepath.stem + ".ocr.md")
        sidecar.write_text("# transcribed")
        return sidecar

    with (
        patch.object(pipeline, "_page_count", return_value=12),
        patch("tools.ocr_scans.ocr_pdf_to_sidecar", side_effect=fake_ocr) as m,
    ):
        assert pipeline.ensure_ocr_sidecar(scan, CFG) is True

    assert scan.with_name("scan.ocr.md").read_text() == "# transcribed"
    assert m.call_args.kwargs["model"] == "gemini-3.5-flash"
    assert m.call_args.kwargs["batch_pages"] == 20


def test_no_api_key_skips_without_raising(scan, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert pipeline.ensure_ocr_sidecar(scan, CFG) is False
    assert not scan.with_name("scan.ocr.md").exists()


def test_over_page_cap_refuses(scan, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with (
        patch.object(pipeline, "_page_count", return_value=401),
        patch("tools.ocr_scans.ocr_pdf_to_sidecar") as m,
    ):
        assert pipeline.ensure_ocr_sidecar(scan, CFG) is False
    m.assert_not_called()


def test_existing_sidecar_is_not_regenerated(scan, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    scan.with_name("scan.ocr.md").write_text("already done")
    with patch("tools.ocr_scans.ocr_pdf_to_sidecar") as m:
        assert pipeline.ensure_ocr_sidecar(scan, CFG) is False
    m.assert_not_called()


def test_ocr_failure_is_swallowed_so_the_run_continues(scan, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with (
        patch.object(pipeline, "_page_count", return_value=3),
        patch("tools.ocr_scans.ocr_pdf_to_sidecar", side_effect=RuntimeError("429")),
    ):
        assert pipeline.ensure_ocr_sidecar(scan, CFG) is False


def test_disabled_is_a_no_op(scan, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    with patch("tools.ocr_scans.ocr_pdf_to_sidecar") as m:
        assert pipeline.ensure_ocr_sidecar(scan, {"ocr": {"enabled": False}}) is False
    m.assert_not_called()
