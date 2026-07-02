"""
Regroupe les fichiers liés avant analyse :
- "Foundations of ML.pdf" + "Foundations of ML Annotated.pdf" → même groupe (cours)
- "CI TD.pdf" + "CI TD Corrected.pdf" → même groupe (TD)
"""
import re
from pathlib import Path

# Suffixes à ignorer pour trouver le nom de base
_STRIP_PATTERNS = re.compile(
    r"\s*(annotated|annoté|corrected|corrigé|solutions?|correction|notes?|slides?)\s*$",
    flags=re.IGNORECASE,
)

# Tags indiquant le type de document
_TD_PATTERNS = re.compile(r"\btd\b|\btp\b|\bexercices?\b|\bworksheet\b", flags=re.IGNORECASE)
_CORRECTED_PATTERNS = re.compile(
    r"\b(corrected|corrigé|solutions?|correction)\b", flags=re.IGNORECASE
)
_ANNOTATED_PATTERNS = re.compile(
    r"\b(annotated|annoté|notes?)\b", flags=re.IGNORECASE
)


def _base_name(filepath: Path) -> str:
    stem = filepath.stem
    return _STRIP_PATTERNS.sub("", stem).strip().lower()


def _doc_type(filepath: Path) -> str:
    name = filepath.stem
    if _CORRECTED_PATTERNS.search(name):
        return "td_corrected"
    if _TD_PATTERNS.search(name):
        return "td"
    if _ANNOTATED_PATTERNS.search(name):
        return "lecture_annotated"
    return "lecture"


class DocumentGroup:
    def __init__(self, base_name: str, folder: Path):
        self.base_name = base_name
        self.folder = folder
        self.files: dict[str, Path] = {}  # doc_type → path

    def add(self, filepath: Path):
        self.files[_doc_type(filepath)] = filepath

    @property
    def all_files(self) -> list[Path]:
        return list(self.files.values())

    def __repr__(self):
        return f"DocumentGroup({self.base_name!r}, {list(self.files.keys())})"


def group_files(files: list[Path]) -> list[DocumentGroup]:
    """
    Grouping: same folder + same stripped base name → same group
    (e.g. "CI TD" + "CI TD Corrected", or a lecture + its annotated version).

    Each document (or lecture+annotated / TD+corrected pair) stays its own group;
    the folder is tracked on the group so the caller can use it as the matière.
    A matière folder holding many chapters therefore yields one group per chapter —
    no file is dropped — and they all share the same folder (→ same matière).
    """
    strict: dict[tuple[Path, str], DocumentGroup] = {}
    for f in files:
        key = (f.parent, _base_name(f))
        if key not in strict:
            strict[key] = DocumentGroup(base_name=_base_name(f), folder=f.parent)
        strict[key].add(f)

    return list(strict.values())
