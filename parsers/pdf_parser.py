from pathlib import Path


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
    return "\n\n".join(texts)
