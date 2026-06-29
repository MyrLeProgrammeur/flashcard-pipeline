import json
from pathlib import Path


class ThemeRegistry:
    """
    Persistance des thèmes canoniques.
    Structure: { "matiere": { "theme_canonique": ["alias1", "alias2"] } }
    """

    def __init__(self, themes_file: Path):
        self.themes_file = themes_file
        self._data: dict[str, dict[str, list[str]]] = self._load()

    def _load(self) -> dict:
        if self.themes_file.exists():
            return json.loads(self.themes_file.read_text())
        return {}

    def save(self):
        self.themes_file.parent.mkdir(parents=True, exist_ok=True)
        self.themes_file.write_text(
            json.dumps(self._data, indent=2, ensure_ascii=False)
        )

    def get_subjects(self) -> list[str]:
        return list(self._data.keys())

    def get_themes(self, subject: str) -> list[str]:
        return list(self._data.get(subject, {}).keys())

    def get_all(self) -> dict:
        return self._data

    def update(self, subject: str, resolved: dict[str, list[str]]):
        """resolved: { canonical_theme: [aliases] }"""
        if subject not in self._data:
            self._data[subject] = {}
        for canonical, aliases in resolved.items():
            if canonical not in self._data[subject]:
                self._data[subject][canonical] = []
            for alias in aliases:
                if alias not in self._data[subject][canonical]:
                    self._data[subject][canonical].append(alias)
        self.save()
