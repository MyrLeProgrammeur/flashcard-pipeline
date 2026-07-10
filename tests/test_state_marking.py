"""
The matière (deck root) is derived from the FOLDER, while the analyst returns its
own content-derived subject. These two strings normally differ. Files must still
be marked processed — otherwise every run re-analyses the whole corpus.
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import token_usage  # noqa: E402
import pipeline  # noqa: E402

# The analyst's subject deliberately differs from the folder name.
FOLDER_NAME = "Foundations_of_ML"
ANALYST_SUBJECT = "Statistical Inference"


def _write_config(tmp_path: Path) -> Path:
    input_dir = tmp_path / "Cours"
    (input_dir / FOLDER_NAME).mkdir(parents=True)
    (input_dir / FOLDER_NAME / "lecture.pdf").write_bytes(b"%PDF-1.4\n%%EOF")

    cfg = {
        "paths": {
            "input_dir": str(input_dir),
            "output_dir": str(tmp_path / "out"),
            "local_output_dir": str(tmp_path / "local"),
            "state_file": str(tmp_path / "state.json"),
            "themes_file": str(tmp_path / "themes.json"),
        },
        "infercom": {
            "base_url": "http://localhost",
            "analyst_model": "m",
            "aggregator_model": "m",
            "builder_model": "m",
            "embed_model": "m",
        },
        "pipeline": {
            "supported_extensions": [".pdf"],
            "max_parallel_files": 1,
            "max_parallel_themes": 1,
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(cfg))
    return config_path


def _analysis():
    return {
        "subject": ANALYST_SUBJECT,
        "themes": [
            {
                "name": "Pivotal Quantities",
                "recall_concepts": ["definition"],
                "problem_types": ["build a CI"],
            }
        ],
        "_usage": token_usage.zero(),
    }


def _fake_write_flashcards(db_path, deck, cards):
    """Stand in for the real writer, but create the deck file: is_processed()
    treats a recorded-but-missing .apkg as unprocessed."""
    Path(db_path).touch()
    return len(cards)


@pytest.fixture
def stubbed(monkeypatch):
    """Stub every outbound call so run_pipeline exercises only its own logic."""
    monkeypatch.setenv("INFERCOM_API_KEY", "test-key")
    with (
        patch.object(pipeline, "OpenAI", MagicMock()),
        patch.object(pipeline, "parse_file", return_value="course content"),
        patch.object(pipeline, "analyze_group", return_value=_analysis()),
        patch.object(
            pipeline,
            "aggregate_themes",
            return_value={
                "resolved": {"Pivotal Quantities": []},
                "new_themes": [],
                "_usage": token_usage.zero(),
            },
        ),
        patch.object(pipeline, "get_existing_questions_for_theme", return_value=[]),
        patch.object(pipeline, "deduplicate_cards", side_effect=lambda c, *a: (c, 0)),
        patch.object(pipeline, "write_flashcards", side_effect=_fake_write_flashcards),
        patch.object(pipeline, "read_all_cards", return_value=[]),
        patch.object(pipeline, "write_markdown"),
        patch.object(pipeline, "write_csv"),
    ):
        yield


def test_files_marked_processed_when_analyst_subject_differs_from_folder(stubbed, tmp_path):
    """Regression: the marking lookup must key on the matière, not the analyst subject."""
    config_path = _write_config(tmp_path)

    with (
        patch.object(
            pipeline,
            "build_recall_flashcards",
            return_value=([{"question": "q", "answer": "a"}], token_usage.zero()),
        ),
        patch.object(pipeline, "build_problem_flashcards", return_value=([], token_usage.zero())),
    ):
        pipeline.run_pipeline(config_path)

    state = pipeline.StateManager(tmp_path / "state.json")
    lecture = tmp_path / "Cours" / FOLDER_NAME / "lecture.pdf"
    assert state.is_processed(lecture), "file built a deck but was never marked processed"


def test_files_not_marked_when_every_build_errors(stubbed, tmp_path):
    """A subject that produced no cards due to errors must stay unprocessed (retry next run)."""
    config_path = _write_config(tmp_path)

    with (
        patch.object(pipeline, "build_recall_flashcards", side_effect=RuntimeError("builder down")),
        patch.object(pipeline, "build_problem_flashcards", side_effect=RuntimeError("builder down")),
    ):
        pipeline.run_pipeline(config_path)

    state = pipeline.StateManager(tmp_path / "state.json")
    lecture = tmp_path / "Cours" / FOLDER_NAME / "lecture.pdf"
    assert not state.is_processed(lecture), "errored build must not lock the file"
