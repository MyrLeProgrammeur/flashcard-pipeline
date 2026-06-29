from pathlib import Path

from .pdf_parser import parse_pdf
from .pptx_parser import parse_pptx


def parse_file(filepath: Path) -> str:
    ext = filepath.suffix.lower()
    if ext == ".pdf":
        return parse_pdf(filepath)
    elif ext in (".pptx", ".ppt"):
        return parse_pptx(filepath)
    elif ext in (".md", ".txt"):
        return filepath.read_text(encoding="utf-8", errors="replace")
    else:
        raise ValueError(f"Extension non supportée: {ext}")
