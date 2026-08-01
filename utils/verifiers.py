"""Evidence verifiers for Atma auto-completion (growth system revamp, SPEC §3).

Each verifier takes (task_row: dict, window_start: datetime, window_end: datetime)
and returns (done: bool, quality: int | None, evidence: str).

Windows are naive *local* datetimes. WHOOP timestamps are UTC and converted;
file mtimes and git commit dates are already local.

All verifiers are fail-open: any internal error is caught and returned as
(False, None, "verifier error: ...") so a broken evidence source can never
block or penalize a task. All DB/file/git access is read-only.
"""

import functools
import os
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Evidence sources (overridable for tests).
WHOOP_DB_PATH = os.environ.get("ATMA_WHOOP_DB", os.path.expanduser("~/whoop-sync/health.db"))
VAULT_ROOT = Path(os.environ.get("ATMA_VAULT", os.path.expanduser("~/Obsidian")))
POETRY_DIR = "07-Poetry"
ROAMINGS_DIR = "Satya's Roamings"
ROAMINGS_INDEX = "!roaming-index.md"
DAILY_NOTES_DIR = "15-Daily-Notes"

SHIP_REPOS = [
    os.path.expanduser("~/edoras"),
    os.path.expanduser("~/omni"),
    os.path.expanduser("~/atma"),
    os.path.expanduser("~/Obsidian"),
]
SHIP_AUTHOR_EMAIL = os.environ.get("ATMA_SHIP_AUTHOR", "patelsatyam100@gmail.com")

MIN_WORKOUT_MINUTES = 20
SPORT_NAMES = {45: "Weightlifting", 63: "Running"}  # other sports accepted too
ESTIMATED_DAILY_INTAKE_KCAL = 2200  # fallback: no intake tracking exists
DEFICIT_MIN_DAYS = 5  # burned > intake on >=5 of 7 days
KJ_TO_KCAL = 0.239006
POEM_JA_RATIO = 0.30
POEM_LONG_LINES = 14

_JA_RE = re.compile(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uff66-\uff9f]")
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*)$")


def _fail_open(fn):
    """Wrap a verifier so exceptions become (False, None, 'verifier error: ...')."""

    @functools.wraps(fn)
    def wrapper(task_row, window_start, window_end):
        try:
            return fn(task_row, window_start, window_end)
        except Exception as e:  # noqa: BLE001 - fail-open by design
            return (False, None, f"verifier error: {e}")

    return wrapper


def _connect_whoop():
    conn = sqlite3.connect(f"file:{WHOOP_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_iso_utc(value):
    """Parse an ISO timestamp string into an aware UTC datetime (None on failure)."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _to_utc(dt):
    """Interpret a naive datetime as system-local and convert to UTC."""
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def _local_mtime(path):
    return datetime.fromtimestamp(path.stat().st_mtime)


# ---------------------------------------------------------------- WHOOP


@_fail_open
def whoop_workout(task_row, window_start, window_end):
    """Any workout in window with duration >= 20 min (sport 45/63 preferred, others accepted).

    Quality: strain >= 10 -> 5, >= 6 -> 4, else 3 (q3 if strain absent).
    """
    ws = _to_utc(window_start).strftime("%Y-%m-%dT%H:%M:%S")
    we = _to_utc(window_end).strftime("%Y-%m-%dT%H:%M:%S.%f")
    with _connect_whoop() as conn:
        rows = conn.execute(
            "SELECT sport_id, start_time, end_time, duration_ms, strain_score "
            "FROM workouts WHERE start_time >= ? AND start_time <= ? ORDER BY start_time",
            (ws, we),
        ).fetchall()

    best = None  # (strain_sort_key, quality, sport_id, minutes, strain)
    for row in rows:
        duration_ms = row["duration_ms"]
        if duration_ms is None:
            # duration_ms is unpopulated in this DB; derive from start/end times.
            start, end = _parse_iso_utc(row["start_time"]), _parse_iso_utc(row["end_time"])
            if start and end:
                duration_ms = (end - start).total_seconds() * 1000
        if duration_ms is None or duration_ms < MIN_WORKOUT_MINUTES * 60 * 1000:
            continue
        strain = row["strain_score"]
        if strain is None:
            quality = 3
        elif strain >= 10:
            quality = 5
        elif strain >= 6:
            quality = 4
        else:
            quality = 3
        candidate = (strain if strain is not None else -1.0, quality, row["sport_id"], duration_ms / 60000, strain)
        if best is None or candidate[0] > best[0]:
            best = candidate

    if best is None:
        return (False, None, f"no workouts >= {MIN_WORKOUT_MINUTES} min in window")
    _, quality, sport_id, minutes, strain = best
    sport = SPORT_NAMES.get(sport_id, f"sport {sport_id}")
    strain_txt = f", strain {strain:.1f}" if strain is not None else ""
    return (True, quality, f"{sport} {minutes:.0f} min{strain_txt}")


@_fail_open
def whoop_deficit(task_row, window_start, window_end):
    """Weekly calorie deficit from WHOOP daily burn vs intake.

    No intake tracking exists, so intake is approximated as 2200 kcal/day and
    the task is done when burned > intake on >= 5 of 7 days. Quality 3-5 by
    average daily deficit size.
    """
    start_date = window_start.date()
    end_date = window_end.date()
    if end_date < start_date:
        return (False, None, "empty window")
    with _connect_whoop() as conn:
        rows = conn.execute(
            "SELECT cycle_date, MAX(kilojoules) AS kj FROM daily_cycles "
            "WHERE cycle_date >= ? AND cycle_date <= ? GROUP BY cycle_date",
            (start_date.isoformat(), end_date.isoformat()),
        ).fetchall()

    burned_by_date = {r["cycle_date"]: (r["kj"] or 0.0) * KJ_TO_KCAL for r in rows}
    total_days = (end_date - start_date).days + 1
    days_above = sum(1 for kcal in burned_by_date.values() if kcal > ESTIMATED_DAILY_INTAKE_KCAL)
    if days_above < DEFICIT_MIN_DAYS:
        return (
            False,
            None,
            f"{days_above}/{total_days} days burned > {ESTIMATED_DAILY_INTAKE_KCAL} kcal baseline "
            f"(need {DEFICIT_MIN_DAYS})",
        )

    total_deficit = sum(kcal - ESTIMATED_DAILY_INTAKE_KCAL for kcal in burned_by_date.values())
    avg_deficit = total_deficit / max(len(burned_by_date), 1)
    if avg_deficit >= 500:
        quality = 5
    elif avg_deficit >= 250:
        quality = 4
    else:
        quality = 3
    return (
        True,
        quality,
        f"{days_above}/{total_days} days in deficit vs {ESTIMATED_DAILY_INTAKE_KCAL} kcal baseline, "
        f"avg deficit {avg_deficit:.0f} kcal/day",
    )


# ---------------------------------------------------------------- vault


def _split_frontmatter(text):
    """Return (frontmatter, body) for a markdown note."""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            return text[3:end], text[end + 4 :]
    return "", text


def _ja_ratio(text):
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return len(_JA_RE.findall(text)) / len(chars)


@_fail_open
def vault_poem(task_row, window_start, window_end):
    """Any .md under 07-Poetry/ (recursive) with mtime in window AND
    (frontmatter `lang: ja` OR >= 30% Japanese chars in body).
    Quality 4 if >= 14 non-empty body lines else 3.
    """
    poetry_dir = VAULT_ROOT / POETRY_DIR
    if not poetry_dir.is_dir():
        return (False, None, f"no poetry dir at {poetry_dir}")
    for path in sorted(poetry_dir.rglob("*.md")):
        if not (window_start <= _local_mtime(path) <= window_end):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        frontmatter, body = _split_frontmatter(text)
        is_ja = re.search(r"(?im)^lang:\s*[\"']?ja[\"']?\s*$", frontmatter) or _ja_ratio(body) >= POEM_JA_RATIO
        if not is_ja:
            continue
        lines = [ln for ln in body.splitlines() if ln.strip()]
        quality = 4 if len(lines) >= POEM_LONG_LINES else 3
        return (True, quality, f"Japanese poem {path.name} ({len(lines)} lines)")
    return (False, None, "no Japanese poem modified in window")


@_fail_open
def vault_roamings(task_row, window_start, window_end):
    """Any new file in Satya's Roamings/ in window (excluding !roaming-index.md)."""
    roamings_dir = VAULT_ROOT / ROAMINGS_DIR
    if not roamings_dir.is_dir():
        return (False, None, f"no roamings dir at {roamings_dir}")
    for path in sorted(roamings_dir.rglob("*.md")):
        if path.name == ROAMINGS_INDEX:
            continue
        # mtime ~ creation for newly written roamings (Linux birth time is unreliable).
        if window_start <= _local_mtime(path) <= window_end:
            return (True, 4, f"new roaming: {path.name}")
    return (False, None, "no new roaming in window")


def _section_lines(text, keywords):
    """Body lines under headings containing any keyword (stops at next heading)."""
    collected = []
    in_section = False
    for line in text.splitlines():
        heading = _HEADING_RE.match(line)
        if heading:
            in_section = any(k in heading.group(1).strip().lower() for k in keywords)
            continue
        if in_section:
            collected.append(line)
    return collected


@_fail_open
def daily_note_reading(task_row, window_start, window_end):
    """The window's first day's daily note has a Reading/Research section with
    >= 3 non-empty lines, OR contains a [[wikilink]]. Quality 3.
    """
    note = VAULT_ROOT / DAILY_NOTES_DIR / f"{window_start.date().isoformat()}.md"
    if not note.is_file():
        return (False, None, f"no daily note {note.name}")
    text = note.read_text(encoding="utf-8", errors="replace")
    non_empty = [ln for ln in _section_lines(text, ("reading", "research")) if ln.strip()]
    if len(non_empty) >= 3:
        return (True, 3, f"{note.name} Reading/Research section ({len(non_empty)} lines)")
    if "[[" in text:
        return (True, 3, f"{note.name} has wikilink(s)")
    return (False, None, f"{note.name}: no Reading/Research section or wikilink")


# ---------------------------------------------------------------- git


@_fail_open
def git_ship(task_row, window_start, window_end):
    """>= 1 commit by SHIP_AUTHOR_EMAIL across the ship repos in window.
    Quality 4 if > 5 commits else 3.
    """
    since = window_start.isoformat()
    until = window_end.isoformat()
    per_repo = {}
    for repo in SHIP_REPOS:
        if not os.path.isdir(os.path.join(repo, ".git")):
            continue
        proc = subprocess.run(
            [
                "git", "-C", repo, "log",
                f"--since={since}", f"--until={until}",
                f"--author={SHIP_AUTHOR_EMAIL}", "--format=%H",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode != 0:
            continue
        count = sum(1 for ln in proc.stdout.splitlines() if ln.strip())
        if count:
            per_repo[os.path.basename(repo.rstrip(os.sep))] = count

    total = sum(per_repo.values())
    if total == 0:
        return (False, None, "no commits by author in window")
    quality = 4 if total > 5 else 3
    breakdown = ", ".join(f"{name}x{n}" for name, n in sorted(per_repo.items()))
    return (True, quality, f"{total} commit(s) shipped ({breakdown})")


# ---------------------------------------------------------------- manual


def manual(task_row, window_start, window_end):
    """Manual-only task: never auto-completes."""
    return (False, None, "manual task")


VERIFIERS = {
    "whoop_workout": whoop_workout,
    "whoop_deficit": whoop_deficit,
    "vault_poem": vault_poem,
    "vault_roamings": vault_roamings,
    "daily_note_reading": daily_note_reading,
    "git_ship": git_ship,
    "manual": manual,
}
