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
    Grouping strategy (in priority order):
    1. Same folder + same stripped base name → same group (e.g. "CI TD" + "CI TD Corrected")
    2. Same folder + different base names → one group per folder (e.g. "Foundations of ML" +
       "Foundations of Machine Learning" in the same folder are treated as one course unit)
    """
    # First pass: strict name-based grouping
    strict: dict[tuple[Path, str], DocumentGroup] = {}
    for f in files:
        key = (f.parent, _base_name(f))
        if key not in strict:
            strict[key] = DocumentGroup(base_name=_base_name(f), folder=f.parent)
        strict[key].add(f)

    # Second pass: merge groups that are in the same folder
    # (different base names in the same folder = same course, different documents)
    by_folder: dict[Path, DocumentGroup] = {}
    for (folder, base), group in strict.items():
        if folder not in by_folder:
            by_folder[folder] = DocumentGroup(base_name=base, folder=folder)
        for doc_type, filepath in group.files.items():
            # Avoid overwriting if same doc_type already exists in folder group
            if doc_type not in by_folder[folder].files:
                by_folder[folder].files[doc_type] = filepath
            else:
                # Suffix the doc_type to keep both
                by_folder[folder].files[f"{doc_type}_2"] = filepath

    return list(by_folder.values())
