"""
OCR fallback generator: turns scanned/handwritten PDFs with no text layer
into a Markdown sidecar `<name>.ocr.md` next to the source PDF.

PC-only tool (never runs on the Termux phone target). Renders each PDF page
to an image and sends the images to a hosted vision model (VLM); the actual
provider call is NOT wired up yet (no vision-capable provider chosen — see
`ocr_images()` below) so this script is a scaffold: everything except the
VLM call itself works today, including --dry-run.

Both flashcard-companion/backend/pdf_context.py and
flashcard-pipeline/parsers/pdf_parser.py already read `<stem>.ocr.md`
sidecars as a fallback when text extraction returns empty.

Target scans (Machine Learning 1 course has none, hence this tool):
    ~/Téléchargements/COURS M1/Cours M1/Machine Learning 1/
        DOC070318-07032018164153.pdf
        DOC180219-18022019094741.pdf
        Documents scannés.pdf
        Slides_25_29.pdf
        Slides_69_77.pdf
        Solution_Ex7.pdf

Sidecars ultimately belong next to the synced copies in
~/Sync/Cours/Machine Learning 1/ so they reach the phone via Syncthing —
either run this script directly against that directory, or copy the
generated `.ocr.md` files there afterwards.

Usage:
    python tools/ocr_scans.py --provider anthropic --model claude-... \\
        "~/Sync/Cours/Machine Learning 1/DOC070318-07032018164153.pdf" \\
        "~/Sync/Cours/Machine Learning 1/Solution_Ex7.pdf"

    # Or set env vars instead of --provider/--api-key/--model:
    OCR_VLM_PROVIDER=anthropic OCR_VLM_API_KEY=sk-... OCR_VLM_MODEL=claude-... \\
        python tools/ocr_scans.py --dry-run "~/Sync/Cours/Machine Learning 1/"*.pdf

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


def ocr_images(images: list[bytes], *, provider: str, api_key: str, model: str) -> str:
    """Send page images to a hosted VLM and return the OCR'd Markdown text.

    # TODO: wire the chosen vision provider (Claude / Gemini / Mistral).
    No vision provider has been picked yet (Infercom, the pipeline's current
    LLM host, has no vision model), so this is intentionally unimplemented.
    Once a provider is chosen: call its vision API with `images` (one call
    per page or batched, provider-dependent), concatenate the per-page
    Markdown transcriptions in page order, and return the result.
    """
    raise NotImplementedError(
        f"ocr_images() not wired up yet for provider={provider!r} model={model!r}. "
        "Pick a vision-capable provider (Claude / Gemini / Mistral) and implement "
        "the API call here."
    )


def ocr_pdf_to_sidecar(
    filepath: Path,
    *,
    provider: str,
    api_key: str,
    model: str,
    dpi: int,
    dry_run: bool,
) -> Path:
    """Render `filepath`'s pages, OCR them, and write the `.ocr.md` sidecar."""
    sidecar = filepath.with_name(filepath.stem + ".ocr.md")

    images = render_pdf_to_images(filepath, dpi=dpi)
    log.info(f"  Rendered {len(images)} page(s) from {filepath.name}")

    if dry_run:
        log.info(f"  [dry-run] would OCR {len(images)} page(s) and write {sidecar}")
        return sidecar

    markdown = ocr_images(images, provider=provider, api_key=api_key, model=model)
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
