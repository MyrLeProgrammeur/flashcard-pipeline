"""
Flashcard pipeline entry point. Launched hourly by systemd timer.
"""
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI
import yaml

from agents.analyst import analyze_group
from agents.aggregator import aggregate_themes
from agents.builder import build_recall_flashcards, build_problem_flashcards
from db_writer import write_flashcards, get_existing_questions_for_theme
from grouper import group_files, DocumentGroup
from parsers import parse_file
from state import StateManager
from themes import ThemeRegistry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_config(config_path: Path) -> dict:
    with open(config_path) as f:
        cfg = yaml.safe_load(f)
    for key in ("input_dir", "output_dir", "state_file", "themes_file"):
        cfg["paths"][key] = str(Path(cfg["paths"][key]).expanduser())
    return cfg


def subject_to_filename(subject: str) -> str:
    safe = re.sub(r"[^\w\s-]", "", subject, flags=re.UNICODE)
    safe = re.sub(r"\s+", "_", safe.strip())
    return f"{safe}.apkg"


def process_group(
    client: anthropic.Anthropic,
    cfg: dict,
    group: DocumentGroup,
    state: StateManager,
) -> dict | None:
    """Parse all files in a group and run the analyst. Returns analysis or None on error."""
    documents = {}
    for doc_type, filepath in group.files.items():
        log.info(f"  Parsing [{doc_type}]: {filepath.name}")
        try:
            content = parse_file(filepath)
            if content.strip():
                documents[doc_type] = (filepath, content)
        except Exception as e:
            log.error(f"  Parse error {filepath.name}: {e}")

    if not documents:
        return None

    log.info(f"Analysing group: {group.base_name!r} ({list(documents.keys())})")
    try:
        result = analyze_group(
            client=client,
            model=cfg["infercom"]["analyst_model"],
            documents=documents,
        )
        log.info(f"  → Subject: {result['subject']} | Themes: {[t['name'] for t in result['themes']]}")
        return result
    except Exception as e:
        log.error(f"  Analyst error [{group.base_name}]: {e}")
        return None


def run_pipeline(config_path: Path = Path("config.yaml")):
    cfg = load_config(config_path)

    input_dir = Path(cfg["paths"]["input_dir"])
    output_dir = Path(cfg["paths"]["output_dir"])
    state_file = Path(cfg["paths"]["state_file"])
    themes_file = Path(cfg["paths"]["themes_file"])

    if not input_dir.exists():
        log.error(f"Input directory not found: {input_dir}")
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    load_dotenv(Path(__file__).parent / ".env")

    state = StateManager(state_file)
    registry = ThemeRegistry(themes_file)
    client = OpenAI(
        base_url=cfg["infercom"]["base_url"],
        api_key=os.environ["INFERCOM_API_KEY"],
    )

    # 1. Detect new files
    all_new = state.get_new_files(input_dir, cfg["pipeline"]["supported_extensions"])
    if not all_new:
        log.info("No new files detected.")
        return

    log.info(f"{len(all_new)} new file(s) to process.")

    # 2. Group related files (lecture + annotated, TD + corrected)
    groups = group_files(all_new)
    log.info(f"Grouped into {len(groups)} document group(s).")

    # 3. Analyse each group in parallel
    analyses: list[tuple[DocumentGroup, dict]] = []
    with ThreadPoolExecutor(max_workers=cfg["pipeline"]["max_parallel_files"]) as ex:
        futures = {
            ex.submit(process_group, client, cfg, g, state): g for g in groups
        }
        for future in as_completed(futures):
            group = futures[future]
            result = future.result()
            if result:
                analyses.append((group, result))

    if not analyses:
        log.warning("No successful analyses.")
        return

    # 4. Group themes by matière — the matière is the FOLDER under input_dir, not
    #    the analyst's content-derived subject (a single chapter would otherwise
    #    become its own matière). The relative folder path becomes the deck root,
    #    with sub-folders mapped to Anki's "::" nesting. The analyst's subject is
    #    kept only for theme extraction, no longer for the deck root.
    def matiere_of(group: DocumentGroup, analysis: dict) -> str:
        try:
            rel = group.folder.relative_to(input_dir)
        except ValueError:
            rel = Path(group.folder.name)
        parts = [p.replace("_", " ").strip() for p in rel.parts if p not in (".", "")]
        if parts:
            return "::".join(parts)
        # File dumped directly in input_dir with no matière folder: fall back to the
        # analyst's subject so the card isn't lost, but flag the missing folder.
        log.warning(f"No matière folder for {group.folder} — using analyst subject.")
        return analysis["subject"]

    by_subject: dict[str, list[tuple[DocumentGroup, list]]] = {}
    for group, analysis in analyses:
        matiere = matiere_of(group, analysis)
        by_subject.setdefault(matiere, []).append((group, analysis["themes"]))

    group_themes_map: dict[str, list[str]] = {}  # group.base_name → canonical themes
    subject_outcome: dict[str, tuple[Path, int, bool]] = {}  # subject → (apkg, total_added, had_error)

    for subject, group_theme_list in by_subject.items():
        existing_themes = registry.get_themes(subject)
        all_proposed = [t["name"] for _, themes in group_theme_list for t in themes]

        log.info(f"[{subject}] Aggregating {len(set(all_proposed))} proposed theme(s) against {len(existing_themes)} existing.")

        try:
            agg_result = aggregate_themes(
                client=client,
                model=cfg["infercom"]["aggregator_model"],
                subject=subject,
                existing_themes=existing_themes,
                proposed_themes=list(set(all_proposed)),
            )
        except Exception as e:
            log.error(f"Aggregator error [{subject}]: {e}")
            continue

        registry.update(subject, agg_result.get("resolved", {}))

        # Build alias → canonical map
        alias_to_canonical: dict[str, str] = {}
        for canonical, aliases in agg_result.get("resolved", {}).items():
            alias_to_canonical[canonical] = canonical
            for alias in aliases:
                alias_to_canonical[alias] = canonical
        for new_theme in agg_result.get("new_themes", []):
            alias_to_canonical[new_theme] = new_theme

        # Collect recall_concepts and problem_types per canonical theme
        canonical_recall: dict[str, list[str]] = {}
        canonical_problems: dict[str, list[str]] = {}

        for group, themes in group_theme_list:
            canonicals_for_group = []
            for t in themes:
                canonical = alias_to_canonical.get(t["name"], t["name"])
                canonicals_for_group.append(canonical)
                canonical_recall.setdefault(canonical, []).extend(t.get("recall_concepts", []))
                canonical_problems.setdefault(canonical, []).extend(t.get("problem_types", []))
            group_themes_map[group.base_name] = list(set(canonicals_for_group))

        db_path = output_dir / subject_to_filename(subject)

        # 5. Build flashcards per theme (parallel)
        def build_theme(canonical: str) -> tuple[str, list[dict], list[dict], bool]:
            errored = False
            recall_existing = get_existing_questions_for_theme(db_path, f"{subject}::{canonical}")
            problem_existing = get_existing_questions_for_theme(db_path, f"{subject}::{canonical}::Problems")
            try:
                recall_cards = build_recall_flashcards(
                    client=client,
                    model=cfg["infercom"]["builder_model"],
                    subject=subject,
                    theme=canonical,
                    recall_concepts=canonical_recall.get(canonical, []),
                    existing_questions=recall_existing,
                )
            except Exception as e:
                log.error(f"Builder [recall/{canonical}]: {e}")
                recall_cards = []
                errored = True

            try:
                problem_cards = build_problem_flashcards(
                    client=client,
                    model=cfg["infercom"]["builder_model"],
                    subject=subject,
                    theme=canonical,
                    problem_types=canonical_problems.get(canonical, []),
                    existing_questions=problem_existing,
                )
            except Exception as e:
                log.error(f"Builder [problems/{canonical}]: {e}")
                problem_cards = []
                errored = True

            return canonical, recall_cards, problem_cards, errored

        all_canonicals = list(set(list(canonical_recall.keys()) + list(canonical_problems.keys())))
        with ThreadPoolExecutor(max_workers=cfg["pipeline"]["max_parallel_themes"]) as ex:
            results = list(ex.map(build_theme, all_canonicals))

        # 6. Write to .db
        total_added = 0
        had_error = False
        for canonical, recall_cards, problem_cards, errored in results:
            had_error = had_error or errored
            if recall_cards:
                deck = f"{subject}::{canonical}"
                n = write_flashcards(db_path, deck, recall_cards)
                log.info(f"  [{deck}] +{n} recall cards")
                total_added += n
            if problem_cards:
                deck = f"{subject}::{canonical}::Problems"
                n = write_flashcards(db_path, deck, problem_cards)
                log.info(f"  [{deck}] +{n} problem cards")
                total_added += n

        log.info(f"[{subject}] Total: {total_added} flashcards added → {db_path.name}")
        subject_outcome[subject] = (db_path, total_added, had_error)

    # 7. Mark files as processed — but never lock a file whose subject built
    #    nothing due to an error (retry next run), and record the .apkg it fed
    #    into so a deleted deck re-qualifies the file for rebuilding.
    for group, analysis in analyses:
        outcome = subject_outcome.get(analysis["subject"])
        if outcome is None:
            continue  # subject skipped (e.g. aggregator error) → retry next run
        db_path, total_added, had_error = outcome
        if had_error and total_added == 0:
            continue  # every build errored out → don't lock, retry next run
        apkg = db_path if total_added > 0 else None
        themes = group_themes_map.get(group.base_name, [])
        for filepath in group.all_files:
            state.mark_processed(filepath, themes, apkg)

    log.info("Pipeline complete.")


if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "config.yaml"
    run_pipeline(config_path)
