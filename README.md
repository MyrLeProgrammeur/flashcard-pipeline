# Flashcard Pipeline

Automatically generates Anki flashcards from your course materials (PDF, PPTX, Markdown) using AI agents.

Drop your slides and TDs into a folder → get organized `.apkg` files in AnkiDroid.

## How it works

```
Your courses (PDF/PPTX)
        ↓  (Syncthing or local folder)
┌─────────────────────────────┐
│  Analyst Agent              │  Reads each file, extracts themes & concepts
│  (gpt-oss-120b)             │  Groups related files (lecture + annotated,
└────────────┬────────────────┘  TD + corrected) as a single unit
             ↓
┌─────────────────────────────┐
│  Theme Aggregator           │  Merges proposed themes with existing registry
│  (gemma-4-31B-it)           │  Avoids creating duplicate themes over time
└────────────┬────────────────┘
             ↓
┌─────────────────────────────┐
│  Flashcard Builder          │  Generates two card types per theme:
│  (gpt-oss-120b)             │  • Recall  — definitions, theorems, formulas
└────────────┬────────────────┘  • Problems — exercise types & solving methods
             ↓
     .apkg files (AnkiDroid)
```

**Incremental**: only new or modified files are processed. Existing Anki scheduling data is preserved on re-import (stable GUIDs).

**Intelligent grouping**: `Lecture.pdf` + `Lecture Annotated.pdf` → analyzed as one unit. `TD.pdf` + `TD Corrected.pdf` → idem.

## Requirements

- Python 3.10+
- Linux (systemd for the 5-minute timer)
- An [Infercom](https://infercom.ai) API key
- [AnkiDroid](https://github.com/ankidroid/Anki-Android) on your phone
- [Syncthing](https://syncthing.net) (optional, for phone sync)

## Installation

```bash
git clone https://github.com/MyrLeProgrammeur/flashcard-pipeline
cd flashcard-pipeline
bash install.sh
```

The installer:
1. Creates a Python virtualenv and installs dependencies
2. Generates a `~/.config/flashcard-pipeline/env` file for your API key
3. Installs a systemd user timer that runs the pipeline every 5 minutes

## Configuration

### 1. API key

Edit `~/.config/flashcard-pipeline/env`:
```
INFERCOM_API_KEY=your-key-here
```

Get your key at [infercom.ai](https://infercom.ai).

### 2. Folder paths

Edit `config.yaml`:
```yaml
paths:
  input_dir: "~/Sync/Cours"             # where you drop your course files
  output_dir: "~/Sync/Flashcards"       # where .apkg files are written (synced)
  local_output_dir: "~/Desktop/flashcards" # .md / .csv exports (local, NOT synced)
```

### 3. Syncthing setup (optional)

- **Cours** folder: sync FROM your devices TO the PC (send-only on phone)
- **Flashcards** folder: sync FROM the PC TO AnkiDroid (`/sdcard/AnkiDroid/`)

## Usage

**Manual run:**
```bash
.venv/bin/python3 pipeline.py
```

**Check the timer:**
```bash
systemctl --user status flashcard-pipeline.timer
```

**Live logs:**
```bash
journalctl --user -u flashcard-pipeline.service -f
```

**Import into AnkiDroid:**  
Open AnkiDroid → Import → select the `.apkg` file from your Flashcards folder.  
Re-importing after new courses are added is safe — scheduling data is preserved.

## Supported file types

| Type | Extension |
|------|-----------|
| PDF slides / lecture notes | `.pdf` |
| PowerPoint | `.pptx`, `.ppt` |
| Markdown notes | `.md` |
| Plain text | `.txt` |

## Output structure

Each run writes **three formats per subject**:

| Format | Where | Synced to phone? | Purpose |
|--------|-------|------------------|---------|
| `.apkg` | `output_dir` (`~/Sync/Flashcards`) | ✅ yes | Import into any Anki client |
| `.md` | `local_output_dir` (`~/Desktop/flashcards`) | ❌ local only | Obsidian, RemNote, plain reading |
| `.csv` | `local_output_dir` (`~/Desktop/flashcards`) | ❌ local only | Quizlet, Notion, spreadsheets |

Only the `.apkg` lands in the Syncthing folder and reaches AnkiDroid. The `.md`
and `.csv` stay on the PC. Both are **full snapshots** read back from the
finished `.apkg`, so they always contain the complete deck (all runs, after
dedup) — not just the cards added in the latest run.

The `.apkg` uses Anki sub-decks:

```
Statistical Inference
  ├── Confidence Intervals          ← recall cards (definitions, theorems)
  │     └── Problems                ← problem-type cards (how to solve X)
  └── Pivotal Quantities
        └── Problems
```

The `.md` and `.csv` flatten the same cards, tagging each with its full deck
path (`Subject::Theme` / `Subject::Theme::Problems`).

> **Note:** `.apkg` is Anki's format, not AnkiDroid-specific — it imports into
> Anki Desktop, AnkiDroid, AnkiMobile (iOS) and AnkiWeb alike. The `.md` / `.csv`
> exports are what let you feed the cards into non-Anki apps.

## Models used

| Role | Model | Why |
|------|-------|-----|
| Analyst + Builder | `gpt-oss-120b` | Best capability/price on Infercom |
| Aggregator | `gemma-4-31B-it` | Lightweight JSON task |

You can change models in `config.yaml`.

## File naming conventions for grouping

The pipeline automatically groups related files in the same folder:

| Pattern | Detected as |
|---------|-------------|
| `X.pdf` + `X Annotated.pdf` | Same lecture (annotated enriches the base) |
| `X TD.pdf` + `X TD Corrected.pdf` | Same problem set (corrections enrich exercises) |
| Any files in the same subfolder | Treated as one course unit |

## License

MIT
