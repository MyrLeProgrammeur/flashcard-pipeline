"""
Full-snapshot exporters: mirror a subject's .apkg contents to local .md and
.csv files. These are written to a local-only directory and are NOT synced to
the phone — the .apkg remains the sole synced output.
"""
import csv as _csv
from pathlib import Path


def _by_deck(cards: list[dict]) -> dict[str, list[dict]]:
    decks: dict[str, list[dict]] = {}
    for c in cards:
        decks.setdefault(c["deck"], []).append(c)
    return decks


def write_markdown(path: Path, subject: str, cards: list[dict]):
    lines = [f"# {subject}", ""]
    decks = _by_deck(cards)
    for deck in sorted(decks):
        lines += [f"## {deck}", ""]
        for c in decks[deck]:
            lines += [f"**Q:** {c['question']}", "", f"**A:** {c['answer']}"]
            if c.get("note"):
                lines += ["", f"> {c['note']}"]
            lines += ["", "---", ""]
    path.write_text("\n".join(lines), encoding="utf-8")


def write_csv(path: Path, subject: str, cards: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(["deck", "question", "answer", "note"])
        for c in cards:
            w.writerow([c["deck"], c["question"], c["answer"], c.get("note", "")])
