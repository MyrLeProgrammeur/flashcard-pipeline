"""
Writes Anki .apkg files (zip of collection.anki2 + media).
One .apkg per subject, sub-decks for themes and problem types.
Stable GUIDs ensure AnkiDroid preserves scheduling on re-import.
"""
import hashlib
import json
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

MODEL_ID = 1699000000000

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS col (
    id INTEGER PRIMARY KEY, crt INTEGER NOT NULL, mod INTEGER NOT NULL,
    scm INTEGER NOT NULL, ver INTEGER NOT NULL, dty INTEGER NOT NULL,
    usn INTEGER NOT NULL, ls INTEGER NOT NULL, conf TEXT NOT NULL,
    models TEXT NOT NULL, decks TEXT NOT NULL, dconf TEXT NOT NULL,
    tags TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY, guid TEXT NOT NULL, mid INTEGER NOT NULL,
    mod INTEGER NOT NULL, usn INTEGER NOT NULL, tags TEXT NOT NULL,
    flds TEXT NOT NULL, sfld TEXT NOT NULL, csum INTEGER NOT NULL,
    flags INTEGER NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    id INTEGER PRIMARY KEY, nid INTEGER NOT NULL, did INTEGER NOT NULL,
    ord INTEGER NOT NULL, mod INTEGER NOT NULL, usn INTEGER NOT NULL,
    type INTEGER NOT NULL, queue INTEGER NOT NULL, due INTEGER NOT NULL,
    ivl INTEGER NOT NULL, factor INTEGER NOT NULL, reps INTEGER NOT NULL,
    lapses INTEGER NOT NULL, left INTEGER NOT NULL, odue INTEGER NOT NULL,
    odid INTEGER NOT NULL, flags INTEGER NOT NULL, data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS revlog (
    id INTEGER PRIMARY KEY, cid INTEGER NOT NULL, usn INTEGER NOT NULL,
    ease INTEGER NOT NULL, ivl INTEGER NOT NULL, lastIvl INTEGER NOT NULL,
    factor INTEGER NOT NULL, time INTEGER NOT NULL, type INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS graves (
    usn INTEGER NOT NULL, oid INTEGER NOT NULL, type INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_cards_nid ON cards (nid);
CREATE INDEX IF NOT EXISTS ix_cards_sched ON cards (did, queue, due);
CREATE INDEX IF NOT EXISTS ix_cards_usn ON cards (usn);
CREATE INDEX IF NOT EXISTS ix_notes_csum ON notes (csum);
CREATE INDEX IF NOT EXISTS ix_notes_usn ON notes (usn);
CREATE INDEX IF NOT EXISTS ix_revlog_cid ON revlog (cid);
CREATE INDEX IF NOT EXISTS ix_revlog_usn ON revlog (usn);
"""

CARD_CSS = """.card {
  font-family: Arial, sans-serif;
  font-size: 18px;
  text-align: left;
  color: #000;
  background-color: #fff;
  padding: 16px;
  max-width: 800px;
  margin: 0 auto;
  line-height: 1.5;
}
hr#answer { margin: 16px 0; border: none; border-top: 1px solid #ccc; }
small { color: #555; }"""


def _guid(subject: str, theme: str, question: str) -> str:
    h = hashlib.sha1(f"{subject}\x1f{theme}\x1f{question}".encode()).digest()
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    num = int.from_bytes(h[:8], "big")
    result = []
    while num:
        result.append(chars[num % 62])
        num //= 62
    return "".join(reversed(result)) or "0"


def _csum(text: str) -> int:
    return int(hashlib.sha1(text[:9].encode()).hexdigest()[:8], 16)


def _deck_id(name: str) -> int:
    val = int.from_bytes(hashlib.sha1(name.encode()).digest()[:6], "big") | (1 << 47)
    return val if val != 1 else val + 2


def _model_json(now: int) -> dict:
    return {
        str(MODEL_ID): {
            "id": MODEL_ID, "name": "Flashcard Pipeline",
            "type": 0, "mod": now, "usn": -1, "sortf": 0, "did": None,
            "tmpls": [{
                "name": "Card 1", "ord": 0,
                "qfmt": "{{Front}}",
                "afmt": "{{FrontSide}}<hr id=answer>{{Back}}"
                        "{{#Note}}<br><small><i>{{Note}}</i></small>{{/Note}}",
                "bqfmt": "", "bafmt": "", "did": None, "bfont": "", "bsize": 0,
            }],
            "flds": [
                {"name": "Front", "ord": 0, "sticky": False, "rtl": False,
                 "font": "Arial", "size": 20, "media": []},
                {"name": "Back", "ord": 1, "sticky": False, "rtl": False,
                 "font": "Arial", "size": 20, "media": []},
                {"name": "Note", "ord": 2, "sticky": False, "rtl": False,
                 "font": "Arial", "size": 14, "media": []},
            ],
            "css": CARD_CSS,
            "latexPre": ("\\documentclass[12pt]{article}\n\\special{papersize=3in,5in}\n"
                         "\\usepackage[utf8]{inputenc}\n\\usepackage{amssymb,amsmath}\n"
                         "\\pagestyle{empty}\n\\setlength{\\parindent}{0in}\n\\begin{document}\n"),
            "latexPost": "\\end{document}",
            "tags": [], "vers": [], "req": [[0, "any", [0]]],
        }
    }


def _default_col_conf() -> dict:
    return {
        "nextPos": 1, "estTimes": True, "activeDecks": [1],
        "sortType": "noteFld", "timeLim": 0, "sortBackwards": False,
        "addToCur": True, "curDeck": 1, "newBury": True,
        "newSpread": 0, "dueCounts": True, "curModel": MODEL_ID,
        "collapseTime": 1200,
    }


def _default_dconf() -> dict:
    return {
        "1": {
            "id": 1, "mod": 0, "name": "Default", "usn": -1,
            "maxTaken": 60, "autoplay": True, "timer": 0, "replayq": True,
            "new": {"bury": True, "delays": [1, 10], "initialFactor": 2500,
                    "ints": [1, 4, 7], "order": 1, "perDay": 20},
            "lapse": {"delays": [10], "leechAction": 0, "leechFails": 8,
                      "minInt": 1, "mult": 0},
            "rev": {"bury": True, "ease4": 1.3, "fuzz": 0.05, "ivlFct": 1,
                    "maxIvl": 36500, "minSpace": 1, "perDay": 200},
        }
    }


def _extract_anki2(apkg_path: Path) -> str:
    """Extract collection.anki2 to a temp file. Returns the temp path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".anki2", delete=False)
    tmp_path = tmp.name
    tmp.close()

    if apkg_path.exists():
        try:
            with zipfile.ZipFile(apkg_path, "r") as zf:
                Path(tmp_path).write_bytes(zf.read("collection.anki2"))
            return tmp_path
        except Exception:
            pass

    # Fresh database
    conn = sqlite3.connect(tmp_path)
    conn.executescript(SCHEMA_SQL)
    now = int(time.time())
    default_decks = {
        "1": {"id": 1, "name": "Default", "conf": 1, "desc": "", "dyn": 0,
              "collapsed": False, "newToday": [0, 0], "revToday": [0, 0],
              "lrnToday": [0, 0], "timeToday": [0, 0], "mod": now, "usn": -1}
    }
    conn.execute(
        "INSERT INTO col VALUES (1,?,?,?,11,0,-1,0,?,?,?,?,'{}')",
        (now, now * 1000, now * 1000,
         json.dumps(_default_col_conf()),
         json.dumps(_model_json(now)),
         json.dumps(default_decks),
         json.dumps(_default_dconf())),
    )
    conn.commit()
    conn.close()
    return tmp_path


def _pack_apkg(tmp_path: str, apkg_path: Path):
    """Pack a collection.anki2 temp file into a .apkg."""
    apkg_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(apkg_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(tmp_path, "collection.anki2")
        zf.writestr("media", "{}")
    Path(tmp_path).unlink(missing_ok=True)


def _ensure_deck(conn: sqlite3.Connection, deck_name: str, now: int) -> int:
    """
    Ensure a deck (and all its parents) exist in col.decks.
    Returns the deck id.
    """
    row = conn.execute("SELECT decks FROM col").fetchone()
    decks: dict = json.loads(row[0])

    did = _deck_id(deck_name)

    if str(did) not in decks:
        # Create all parent decks first
        parts = deck_name.split("::")
        for i in range(1, len(parts) + 1):
            parent_name = "::".join(parts[:i])
            parent_id = _deck_id(parent_name)
            if str(parent_id) not in decks:
                decks[str(parent_id)] = {
                    "id": parent_id, "name": parent_name, "conf": 1,
                    "desc": "", "dyn": 0, "collapsed": False,
                    "newToday": [0, 0], "revToday": [0, 0],
                    "lrnToday": [0, 0], "timeToday": [0, 0],
                    "mod": now, "usn": -1,
                }
        conn.execute("UPDATE col SET decks=?, mod=?", (json.dumps(decks), now * 1000))

    return did


def _get_existing_guids(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT guid FROM notes")}


def _get_existing_questions(conn: sqlite3.Connection, did: int) -> list[str]:
    rows = conn.execute(
        "SELECT n.flds FROM notes n JOIN cards c ON c.nid = n.id WHERE c.did = ?",
        (did,)
    ).fetchall()
    return [r[0].split("\x1f")[0] for r in rows]


def _max_due(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(due) FROM cards WHERE type=0").fetchone()
    return (row[0] or 0) + 1


# ── Public API ─────────────────────────────────────────────────────────────────

def write_flashcards(apkg_path: Path, deck_name: str, flashcards: list[dict]) -> int:
    """
    Add flashcards to an .apkg under deck `deck_name`.
    Creates the .apkg if it doesn't exist. Preserves existing cards.
    Returns the number of new cards added.
    """
    tmp_path = _extract_anki2(apkg_path)
    conn = sqlite3.connect(tmp_path)
    now = int(time.time())

    did = _ensure_deck(conn, deck_name, now)
    existing_guids = _get_existing_guids(conn)
    due = _max_due(conn)

    # Subject = everything before the first "::"
    subject = deck_name.split("::")[0]

    # Base IDs on max existing to avoid collisions across sequential calls
    max_nid = conn.execute("SELECT MAX(id) FROM notes").fetchone()[0] or 0
    max_cid = conn.execute("SELECT MAX(id) FROM cards").fetchone()[0] or 0
    base_nid = max(max_nid + 1, int(time.time() * 1000))
    base_cid = max(max_cid + 1, base_nid + 100000)

    added = 0
    for card in flashcards:
        q = card.get("question", "").strip()
        a = card.get("answer", "").strip()
        n = card.get("note", "").strip()
        if not q or not a:
            continue

        guid = _guid(subject, deck_name, q)
        if guid in existing_guids:
            continue

        flds = f"{q}\x1f{a}\x1f{n}"
        nid = base_nid + added
        cid = base_cid + added

        conn.execute(
            "INSERT INTO notes VALUES (?,?,?,?,?,?,?,?,?,0,'')",
            (nid, guid, MODEL_ID, now, -1, "", flds, q, _csum(q)),
        )
        conn.execute(
            "INSERT INTO cards VALUES (?,?,?,0,?,?,0,0,?,0,2500,0,0,0,0,0,0,'')",
            (cid, nid, did, now, -1, due),
        )
        existing_guids.add(guid)
        due += 1
        added += 1

    conn.commit()
    conn.close()
    _pack_apkg(tmp_path, apkg_path)
    return added


def get_existing_questions_for_theme(apkg_path: Path, deck_name: str) -> list[str]:
    """Return existing questions for a deck in the .apkg."""
    if not apkg_path.exists():
        return []
    tmp_path = _extract_anki2(apkg_path)
    conn = sqlite3.connect(tmp_path)
    try:
        did = _deck_id(deck_name)
        return _get_existing_questions(conn, did)
    except Exception:
        return []
    finally:
        conn.close()
        Path(tmp_path).unlink(missing_ok=True)
