"""
OCR fallback generator: turns scanned/handwritten PDFs with no text layer
into a Markdown sidecar `<name>.ocr.md` next to the source PDF.

PC-only tool (never runs on the Termux phone target). Renders each PDF page to
an image and sends the images to Google Gemini via its OpenAI-compatible
endpoint, in batches of `DEFAULT_BATCH_PAGES` pages per request.

pipeline.py calls this automatically when a PDF yields no text and has no
sidecar yet; running it by hand is only needed to pre-generate or re-generate
a sidecar.

Both flashcard-companion/backend/pdf_context.py and
flashcard-pipeline/parsers/pdf_parser.py already read `<stem>.ocr.md`
sidecars as a fallback when text extraction returns empty.

Typical use case: a course folder has scanned/handwritten PDFs with no
text layer (e.g. lecture photos, scanned exercise sheets) mixed in with
regular text-layer PDFs.

Sidecars ultimately belong next to the synced copies in the input
directory (see `config.yaml`'s `input_dir`) so they reach the app via
Syncthing — either run this script directly against that directory, or
copy the generated `.ocr.md` files there afterwards.

Usage:
    python tools/ocr_scans.py --provider anthropic --model claude-... \\
        "~/Sync/Cours/Some Course/scan1.pdf" \\
        "~/Sync/Cours/Some Course/scan2.pdf"

    # Or set env vars instead of --provider/--api-key/--model:
    OCR_VLM_PROVIDER=anthropic OCR_VLM_API_KEY=sk-... OCR_VLM_MODEL=claude-... \\
        python tools/ocr_scans.py --dry-run "~/Sync/Cours/Some Course/"*.pdf

Requires (PC only, do NOT add to the Termux backend/requirements.txt):
    pip install pymupdf
"""
import argparse
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def render_pdf_to_images(filepath: Path, dpi: int = 200) -> list[bytes]:
    """Render each page of a PDF to a PNG image (bytes), for VLM input."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ImportError(
            "PyMuPDF requis pour le rendu PDF->image: pip install pymupdf"
        )

    images = []
    zoom = dpi / 72
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(filepath) as doc:
        for page in doc:
            pix = page.get_pixmap(matrix=matrix)
            images.append(pix.tobytes("png"))
    return images


OCR_PROMPT = (
    "You are an OCR engine for scanned/handwritten university mathematics — "
    "lecture notes, exercise sheets and exam solutions. Transcribe ALL content "
    "of the following page image(s) into clean Markdown, in reading order. "
    "Render every mathematical expression in LaTeX: $...$ for inline, $$...$$ "
    "for display equations. Preserve structure (headings, numbered problems, "
    "solution steps, lists). Transcribe faithfully; do not solve, summarise or "
    "add commentary. If something is illegible, write [illegible]. Output only "
    "the transcription."
)


#: Pages per request. Inline base64 images are the binding constraint (Gemini
#: rejects requests over ~20 MB), not the model's token limit — a 200-page deck
#: at 200 dpi is ~100 MB if sent whole. Batching keeps any document OCR-able.
DEFAULT_BATCH_PAGES = 20


def ocr_images(
    images: list[bytes],
    *,
    provider: str,
    api_key: str,
    model: str,
    batch_pages: int = DEFAULT_BATCH_PAGES,
) -> str:
    """Send page images to a hosted VLM and return the OCR'd Markdown text.

    Wired for Google Gemini via its OpenAI-compatible endpoint (reuses the
    `openai` SDK already in requirements — no extra dependency). Pages are sent
    in order, `batch_pages` at a time, and the transcriptions are concatenated.
    """
    if provider not in ("google", "gemini"):
        raise NotImplementedError(
            f"ocr_images() is wired for Gemini only; got provider={provider!r}. "
            "Add the API call for Claude/Mistral here if you switch provider."
        )

    import base64

    from openai import OpenAI

    client = OpenAI(
        api_key=api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )

    chunks: list[str] = []
    for start in range(0, len(images), batch_pages):
        batch = images[start : start + batch_pages]
        content = [{"type": "text", "text": OCR_PROMPT}]
        for img in batch:
            b64 = base64.b64encode(img).decode()
            content.append(
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}
            )

        log.info(f"  OCR pages {start + 1}-{start + len(batch)} of {len(images)}")
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": content}],
        )
        chunks.append(resp.choices[0].message.content or "")

    return "\n\n".join(c.strip() for c in chunks if c.strip())


def ocr_pdf_to_sidecar(
    filepath: Path,
    *,
    provider: str,
    api_key: str,
    model: str,
    dpi: int,
    dry_run: bool,
    batch_pages: int = DEFAULT_BATCH_PAGES,
) -> Path:
    """Render `filepath`'s pages, OCR them, and write the `.ocr.md` sidecar."""
    sidecar = filepath.with_name(filepath.stem + ".ocr.md")

    images = render_pdf_to_images(filepath, dpi=dpi)
    log.info(f"  Rendered {len(images)} page(s) from {filepath.name}")

    if dry_run:
        log.info(f"  [dry-run] would OCR {len(images)} page(s) and write {sidecar}")
        return sidecar

    markdown = ocr_images(
        images, provider=provider, api_key=api_key, model=model, batch_pages=batch_pages
    )
    if not markdown.strip():
        raise RuntimeError(f"OCR returned no text for {filepath.name}")
    sidecar.write_text(markdown, encoding="utf-8")
    log.info(f"  Wrote {sidecar}")
    return sidecar


def main() -> int:
    parser = argparse.ArgumentParser(
        description="OCR scanned/handwritten PDFs into `<name>.ocr.md` sidecars.",
    )
    parser.add_argument("pdfs", nargs="+", help="Path(s) to source PDF(s).")
    parser.add_argument(
        "--provider",
        default=os.environ.get("OCR_VLM_PROVIDER"),
        help="Vision provider name (e.g. anthropic, google, mistral). "
        "Defaults to $OCR_VLM_PROVIDER.",
    )
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OCR_VLM_API_KEY"),
        help="API key for the vision provider. Defaults to $OCR_VLM_API_KEY. "
        "Never hardcode this.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OCR_VLM_MODEL"),
        help="Vision model name. Defaults to $OCR_VLM_MODEL.",
    )
    parser.add_argument(
        "--dpi",
        type=int,
        default=200,
        help="Render resolution for PDF pages (default: 200).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render pages and report what would be OCR'd, but skip the VLM "
        "call and don't write sidecars.",
    )
    args = parser.parse_args()

    if not args.dry_run and not (args.provider and args.api_key and args.model):
        parser.error(
            "--provider/--api-key/--model (or $OCR_VLM_PROVIDER/$OCR_VLM_API_KEY/"
            "$OCR_VLM_MODEL) are required unless --dry-run is set."
        )

    exit_code = 0
    for raw_path in args.pdfs:
        filepath = Path(raw_path).expanduser()
        if not filepath.exists():
            log.error(f"Not found, skipping: {filepath}")
            exit_code = 1
            continue

        log.info(f"Processing {filepath.name}")
        try:
            ocr_pdf_to_sidecar(
                filepath,
                provider=args.provider,
                api_key=args.api_key,
                model=args.model,
                dpi=args.dpi,
                dry_run=args.dry_run,
            )
        except ImportError as e:
            log.error(f"  {e}")
            exit_code = 1
        except NotImplementedError as e:
            log.error(f"  {e}")
            exit_code = 1
        except Exception as e:
            log.error(f"  Failed on {filepath.name}: {e}")
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
