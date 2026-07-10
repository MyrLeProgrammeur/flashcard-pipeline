"""
Rebuild `processed_files.json` for files whose deck already exists.

A bug in the marking step (fixed) meant `mark_processed()` never ran, so the
state file is empty even though decks were built. Without this backfill the
next run treats the whole corpus as new and re-bills every file to the LLM.

A file is marked only if its content actually reached the deck. mtime is NOT a
usable signal here: five folders carry a single uniform `2026-07-03 09:51` stamp
from a bulk copy that post-dates the decks built from them, so "newer than the
deck" is a copy artifact, not an edit.

The two real exclusions:
  * a scanned PDF with an `.ocr.md` sidecar — the sidecar was written after the
    deck, so the PDF parsed to empty text at build time and was never analysed.
  * a file loose in input_dir with no matière folder.

Themes are recorded as `[]`: the real per-file theme lists only ever existed in
memory during the original runs. `is_processed()` reads only `hash` and `apkg`,
so this is functionally correct.

    python tools/backfill_state.py --dry-run
    python tools/backfill_state.py
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import load_config, subject_to_filename  # noqa: E402
from state import StateManager  # noqa: E402


def matiere_of(folder: Path, input_dir: Path) -> str | None:
    """Mirror pipeline.matiere_of: the matière is the folder path under input_dir.
    Returns None for a file sitting directly in input_dir (no matière folder)."""
    try:
        rel = folder.relative_to(input_dir)
    except ValueError:
        return None
    parts = [p.replace("_", " ").strip() for p in rel.parts if p not in (".", "")]
    return "::".join(parts) if parts else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--config", default=str(Path(__file__).resolve().parent.parent / "config.yaml"))
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    input_dir = Path(cfg["paths"]["input_dir"])
    output_dir = Path(cfg["paths"]["output_dir"])
    state = StateManager(Path(cfg["paths"]["state_file"]))

    marked, skipped = [], []

    for ext in cfg["pipeline"]["supported_extensions"]:
        for f in sorted(input_dir.rglob(f"*{ext}")):
            if f.name.startswith(".syncthing") or f.name.startswith("syncthing-"):
                continue

            if f.name.endswith(".ocr.md"):
                skipped.append((f, "OCR sidecar — an output, never an input"))
                continue

            matiere = matiere_of(f.parent, input_dir)
            if matiere is None:
                skipped.append((f, "no matière folder (loose in input_dir)"))
                continue

            apkg = output_dir / subject_to_filename(matiere)
            if not apkg.exists():
                skipped.append((f, f"no deck: {apkg.name}"))
                continue

            sidecar = f.with_name(f.stem + ".ocr.md")
            if sidecar.exists() and sidecar.stat().st_mtime > apkg.stat().st_mtime:
                skipped.append((f, "scan OCR'd after the deck — never analysed"))
                continue

            marked.append((f, apkg))
            if not args.dry_run:
                state.mark_processed(f, themes=[], apkg=apkg)

    print(f"\n=== MARK ({len(marked)}) ===")
    for f, apkg in marked:
        print(f"  {f.relative_to(input_dir)}  →  {apkg.name}")

    print(f"\n=== SKIP ({len(skipped)}) ===")
    for f, why in skipped:
        print(f"  {f.relative_to(input_dir)}  —  {why}")

    print(f"\n{len(marked)} marked, {len(skipped)} skipped.")
    if args.dry_run:
        print("Dry run — nothing written.")
    else:
        print(f"Written to {cfg['paths']['state_file']}")


if __name__ == "__main__":
    main()
