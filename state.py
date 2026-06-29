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
        if key not in self._data:
            return False
        return self._data[key]["hash"] == file_hash(filepath)

    def mark_processed(self, filepath: Path, themes: list[str]):
        self._data[str(filepath)] = {
            "hash": file_hash(filepath),
            "themes": themes,
        }
        _save(self.state_file, self._data)

    def get_new_files(self, input_dir: Path, extensions: list[str]) -> list[Path]:
        new_files = []
        for ext in extensions:
            for f in input_dir.rglob(f"*{ext}"):
                if f.name.startswith(".syncthing") or f.name.startswith("syncthing-"):
                    continue
                if not self.is_processed(f):
                    new_files.append(f)
        return new_files
