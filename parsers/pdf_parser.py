from pathlib import Path


def _read_ocr_sidecar(filepath: Path) -> str:
    """Read the `<stem>.ocr.md` sidecar next to a scanned PDF, if present.

    Scanned/handwritten PDFs have no text layer, so extraction returns empty.
    A hosted VLM can pre-OCR such PDFs into a Markdown sidecar (see
    tools/ocr_scans.py); this is the read-side fallback.
    """
    sidecar = filepath.with_name(filepath.stem + ".ocr.md")
    try:
        return sidecar.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def parse_pdf(filepath: Path) -> str:
    try:
        import pdfplumber
    except ImportError:
        raise ImportError("pdfplumber requis: pip install pdfplumber")

    texts = []
    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                texts.append(text.strip())
    result = "\n\n".join(texts)
    if result.strip():
        return result
    return _read_ocr_sidecar(filepath)
