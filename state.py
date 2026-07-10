import hashlib
import json
import os
from pathlib import Path


def _load(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def file_hash(filepath: Path) -> str:
    h = hashlib.sha256()
    h.update(filepath.read_bytes())
    return h.hexdigest()


class StateManager:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self._data = _load(state_file)

    def is_processed(self, filepath: Path) -> bool:
        key = str(filepath)
        entry = self._data.get(key)
        if entry is None or entry["hash"] != file_hash(filepath):
            return False
        # The output this file fed into was recorded but no longer exists
        # (deck deleted / never synced) → treat as unprocessed so it rebuilds.
        apkg = entry.get("apkg")
        if apkg and not Path(apkg).exists():
            return False
        return True

    def mark_processed(self, filepath: Path, themes: list[str], apkg: Path | None = None):
        self._data[str(filepath)] = {
            "hash": file_hash(filepath),
            "themes": themes,
            "apkg": str(apkg) if apkg else None,
        }
        _save(self.state_file, self._data)

    def get_new_files(self, input_dir: Path, extensions: list[str]) -> list[Path]:
        new_files = []
        for ext in extensions:
            for f in input_dir.rglob(f"*{ext}"):
                if f.name.startswith(".syncthing") or f.name.startswith("syncthing-"):
                    continue
                # `.ocr.md` is a sidecar produced by tools/ocr_scans.py and read
                # back by parsers/pdf_parser.py — it is an output, not a course.
                if f.name.endswith(".ocr.md"):
                    continue
                if not self.is_processed(f):
                    new_files.append(f)
        return new_files
