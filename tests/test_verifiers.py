import os, sys
os.environ.setdefault("SUPABASE_URL", "https://fake-project.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "aaa.bbb.ccc")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sqlite3
import subprocess
from datetime import date, datetime, time, timedelta, timezone
from unittest.mock import MagicMock

import pytest

import utils.verifiers as verifiers
from utils.verifiers import VERIFIERS
import scripts.auto_verify as auto_verify
import main as main_module


# ---------------------------------------------------------------- helpers

def day_window(day, days=1):
    """Naive local window: [day 00:00, last day 23:59:59.999999]."""
    start = datetime.combine(day, time.min)
    end = datetime.combine(day + timedelta(days=days - 1), time.max)
    return start, end


def as_whoop_ts(local_dt):
    """Format a naive local datetime the way the WHOOP DB stores it (UTC, Z-suffixed)."""
    return local_dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"


def make_whoop_db(tmp_path, workouts=(), cycles=()):
    db = tmp_path / "health.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE workouts (workout_id TEXT, start_time TEXT, end_time TEXT, "
        "duration_ms INTEGER, strain_score REAL, sport_id INTEGER)"
    )
    conn.execute("CREATE TABLE daily_cycles (cycle_id INTEGER PRIMARY KEY, cycle_date TEXT, kilojoules REAL)")
    for i, w in enumerate(workouts):
        conn.execute(
            "INSERT INTO workouts VALUES (?, ?, ?, ?, ?, ?)",
            (f"w{i}", w.get("start"), w.get("end"), w.get("duration_ms"), w.get("strain"), w.get("sport_id")),
        )
    for i, (cycle_date, kj) in enumerate(cycles):
        conn.execute("INSERT INTO daily_cycles VALUES (?, ?, ?)", (i, cycle_date, kj))
    conn.commit()
    conn.close()
    return db


def set_mtime(path, local_dt):
    ts = local_dt.timestamp()
    os.utime(path, (ts, ts))


def kj_for_kcal(kcal):
    return kcal / verifiers.KJ_TO_KCAL


WED = date(2026, 7, 29)  # arbitrary Wednesday


# ---------------------------------------------------------------- whoop_workout

def test_whoop_workout_done_high_strain(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    start = datetime.combine(WED, time(10, 0))
    db = make_whoop_db(tmp_path, workouts=[{
        "start": as_whoop_ts(start), "end": as_whoop_ts(start + timedelta(minutes=45)),
        "duration_ms": None, "strain": 11.2, "sport_id": 45,
    }])
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_workout({}, ws, we)
    assert done is True and q == 5
    assert "strain 11.2" in ev and "45 min" in ev


def test_whoop_workout_quality_bands_and_other_sports(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    start = datetime.combine(WED, time(10, 0))
    db = make_whoop_db(tmp_path, workouts=[
        {"start": as_whoop_ts(start), "end": as_whoop_ts(start + timedelta(minutes=30)),
         "duration_ms": None, "strain": 7.0, "sport_id": 63},   # -> q4
        {"start": as_whoop_ts(start + timedelta(hours=3)), "end": as_whoop_ts(start + timedelta(hours=4)),
         "duration_ms": None, "strain": 3.0, "sport_id": 36},   # other sport, accepted -> q3
    ])
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_workout({}, ws, we)
    assert done is True and q == 4  # highest-strain qualifying workout wins
    assert "Running" in ev


def test_whoop_workout_uses_duration_ms_when_present(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    db = make_whoop_db(tmp_path, workouts=[{
        "start": as_whoop_ts(datetime.combine(WED, time(10, 0))), "end": None,
        "duration_ms": 25 * 60 * 1000, "strain": None, "sport_id": 45,
    }])
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_workout({}, ws, we)
    assert done is True and q == 3  # no strain -> q3


def test_whoop_workout_empty_window(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    other_day = datetime.combine(WED - timedelta(days=5), time(10, 0))
    db = make_whoop_db(tmp_path, workouts=[
        # outside the window
        {"start": as_whoop_ts(other_day), "end": as_whoop_ts(other_day + timedelta(hours=1)),
         "duration_ms": None, "strain": 12.0, "sport_id": 45},
        # in window but too short
        {"start": as_whoop_ts(datetime.combine(WED, time(10, 0))),
         "end": as_whoop_ts(datetime.combine(WED, time(10, 10))),
         "duration_ms": None, "strain": 12.0, "sport_id": 45},
    ])
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_workout({}, ws, we)
    assert done is False and q is None
    assert "no workouts" in ev


# ---------------------------------------------------------------- whoop_deficit

def _week_cycles(kcals, start=WED - timedelta(days=WED.weekday())):
    return [((start + timedelta(days=i)).isoformat(), kj_for_kcal(k)) for i, k in enumerate(kcals)]


def test_whoop_deficit_done_quality5(tmp_path, monkeypatch):
    ws, we = day_window(WED - timedelta(days=WED.weekday()), days=7)  # Mon-Sun week
    db = make_whoop_db(tmp_path, cycles=_week_cycles([3000] * 6 + [1000]))
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_deficit({}, ws, we)
    assert done is True and q == 5  # avg deficit ~514 kcal/day
    assert "6/7 days" in ev


def test_whoop_deficit_done_quality3(tmp_path, monkeypatch):
    ws, we = day_window(WED - timedelta(days=WED.weekday()), days=7)
    db = make_whoop_db(tmp_path, cycles=_week_cycles([2300] * 5 + [2000, 2100]))
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_deficit({}, ws, we)
    assert done is True and q == 3


def test_whoop_deficit_not_enough_days(tmp_path, monkeypatch):
    ws, we = day_window(WED - timedelta(days=WED.weekday()), days=7)
    db = make_whoop_db(tmp_path, cycles=_week_cycles([3000] * 4 + [1500] * 3))
    monkeypatch.setattr(verifiers, "WHOOP_DB_PATH", str(db))
    done, q, ev = verifiers.whoop_deficit({}, ws, we)
    assert done is False and q is None
    assert "4/7 days" in ev


# ---------------------------------------------------------------- vault_poem

def _poetry_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(verifiers, "VAULT_ROOT", tmp_path)
    d = tmp_path / verifiers.POETRY_DIR
    d.mkdir(parents=True)
    return d


def test_vault_poem_frontmatter_lang_ja_long(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    d = _poetry_dir(tmp_path, monkeypatch)
    body = "\n".join(f"line {i}" for i in range(15))
    p = d / "poem.md"
    p.write_text(f"---\nlang: ja\n---\n{body}\n", encoding="utf-8")
    set_mtime(p, datetime.combine(WED, time(12, 0)))
    done, q, ev = verifiers.vault_poem({}, ws, we)
    assert done is True and q == 4
    assert "poem.md" in ev and "15 lines" in ev


def test_vault_poem_japanese_chars_short(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    d = _poetry_dir(tmp_path, monkeypatch)
    p = d / "短い詩.md"
    p.write_text("静けさの中で\n考える\n", encoding="utf-8")  # >30% Japanese, 2 lines
    set_mtime(p, datetime.combine(WED, time(12, 0)))
    done, q, ev = verifiers.vault_poem({}, ws, we)
    assert done is True and q == 3


def test_vault_poem_empty_window(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    d = _poetry_dir(tmp_path, monkeypatch)
    p = d / "old.md"
    p.write_text("---\nlang: ja\n---\n" + "\n".join(f"line {i}" for i in range(15)), encoding="utf-8")
    set_mtime(p, datetime.combine(WED - timedelta(days=10), time(12, 0)))  # outside window
    done, q, ev = verifiers.vault_poem({}, ws, we)
    assert done is False and q is None


def test_vault_poem_not_japanese(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    d = _poetry_dir(tmp_path, monkeypatch)
    p = d / "english.md"
    p.write_text("roses are red\nviolets are blue\n", encoding="utf-8")
    set_mtime(p, datetime.combine(WED, time(12, 0)))
    done, q, ev = verifiers.vault_poem({}, ws, we)
    assert done is False and q is None


# ---------------------------------------------------------------- vault_roamings

def test_vault_roamings_done(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    monkeypatch.setattr(verifiers, "VAULT_ROOT", tmp_path)
    d = tmp_path / verifiers.ROAMINGS_DIR
    d.mkdir(parents=True)
    p = d / "2026-07-29 - Emergence.md"
    p.write_text("# Emergence\n", encoding="utf-8")
    set_mtime(p, datetime.combine(WED, time(9, 0)))
    done, q, ev = verifiers.vault_roamings({}, ws, we)
    assert done is True and q == 4
    assert "Emergence" in ev


def test_vault_roamings_empty_window(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    monkeypatch.setattr(verifiers, "VAULT_ROOT", tmp_path)
    d = tmp_path / verifiers.ROAMINGS_DIR
    d.mkdir(parents=True)
    idx = d / verifiers.ROAMINGS_INDEX
    idx.write_text("index\n", encoding="utf-8")
    set_mtime(idx, datetime.combine(WED, time(9, 0)))  # index file is excluded
    old = d / "old.md"
    old.write_text("old\n", encoding="utf-8")
    set_mtime(old, datetime.combine(WED - timedelta(days=3), time(9, 0)))
    done, q, ev = verifiers.vault_roamings({}, ws, we)
    assert done is False and q is None


# ---------------------------------------------------------------- daily_note_reading

def _daily_note(tmp_path, monkeypatch, day, text):
    monkeypatch.setattr(verifiers, "VAULT_ROOT", tmp_path)
    d = tmp_path / verifiers.DAILY_NOTES_DIR
    d.mkdir(parents=True)
    p = d / f"{day.isoformat()}.md"
    p.write_text(text, encoding="utf-8")
    return p


def test_daily_note_reading_section(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    _daily_note(tmp_path, monkeypatch, WED, "# Daily\n\n## Reading\n\n- book a\n- paper b\n- article c\n")
    done, q, ev = verifiers.daily_note_reading({}, ws, we)
    assert done is True and q == 3
    assert "Reading/Research section" in ev


def test_daily_note_reading_wikilink(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    _daily_note(tmp_path, monkeypatch, WED, "# Daily\n\nThoughts on [[Emergence]] today.\n")
    done, q, ev = verifiers.daily_note_reading({}, ws, we)
    assert done is True and q == 3
    assert "wikilink" in ev


def test_daily_note_reading_empty(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    # short section (2 lines) and no wikilink -> not done
    _daily_note(tmp_path, monkeypatch, WED, "# Daily\n\n## Reading\n\n- one\n- two\n\n## Other\n\nx\n")
    done, q, ev = verifiers.daily_note_reading({}, ws, we)
    assert done is False and q is None


def test_daily_note_reading_no_note(tmp_path, monkeypatch):
    ws, we = day_window(WED)
    monkeypatch.setattr(verifiers, "VAULT_ROOT", tmp_path)
    done, q, ev = verifiers.daily_note_reading({}, ws, we)
    assert done is False and q is None
    assert "no daily note" in ev


# ---------------------------------------------------------------- git_ship

def _git_repo(path, commits, email, when):
    subprocess.run(["git", "init", "-q"], cwd=path, check=True, capture_output=True)
    for i in range(commits):
        (path / f"f{i}.txt").write_text(str(i))
        subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True)
        env = dict(os.environ, GIT_AUTHOR_DATE=when.isoformat(), GIT_COMMITTER_DATE=when.isoformat())
        subprocess.run(
            ["git", "-c", "user.name=Test", "-c", f"user.email={email}", "commit", "-q", "-m", f"c{i}"],
            cwd=path, check=True, capture_output=True, env=env,
        )


def test_git_ship_done(tmp_path, monkeypatch):
    ws, we = day_window(WED, days=7)
    repo = tmp_path / "edoras"
    repo.mkdir()
    _git_repo(repo, 2, "patelsatyam100@gmail.com", datetime.combine(WED, time(15, 0)))
    monkeypatch.setattr(verifiers, "SHIP_REPOS", [str(repo)])
    done, q, ev = verifiers.git_ship({}, ws, we)
    assert done is True and q == 3
    assert "2 commit(s)" in ev and "edorasx2" in ev


def test_git_ship_many_commits_quality4(tmp_path, monkeypatch):
    ws, we = day_window(WED, days=7)
    repo = tmp_path / "omni"
    repo.mkdir()
    _git_repo(repo, 6, "patelsatyam100@gmail.com", datetime.combine(WED, time(15, 0)))
    monkeypatch.setattr(verifiers, "SHIP_REPOS", [str(repo)])
    done, q, ev = verifiers.git_ship({}, ws, we)
    assert done is True and q == 4


def test_git_ship_empty_window(tmp_path, monkeypatch):
    ws, we = day_window(WED, days=7)
    repo = tmp_path / "atma"
    repo.mkdir()
    # commits by another author only
    _git_repo(repo, 2, "someone-else@example.com", datetime.combine(WED, time(15, 0)))
    monkeypatch.setattr(verifiers, "SHIP_REPOS", [str(repo), str(tmp_path / "nonexistent")])
    done, q, ev = verifiers.git_ship({}, ws, we)
    assert done is False and q is None


# ---------------------------------------------------------------- manual & registry

def test_manual_never_done():
    assert verifiers.manual({}, None, None) == (False, None, "manual task")
    assert VERIFIERS["manual"] is verifiers.manual


def test_registry_keys():
    assert set(VERIFIERS) == {
        "whoop_workout", "whoop_deficit", "vault_poem", "vault_roamings",
        "daily_note_reading", "git_ship", "manual",
    }


# ---------------------------------------------------------------- fail-open

def test_fail_open_decorator():
    @verifiers._fail_open
    def boom(task_row, ws, we):
        raise ValueError("nope")

    assert boom({}, None, None) == (False, None, "verifier error: nope")


def test_verifier_error_fails_open(monkeypatch):
    monkeypatch.setattr(verifiers.sqlite3, "connect", MagicMock(side_effect=RuntimeError("db gone")))
    ws, we = day_window(WED)
    done, q, ev = verifiers.whoop_workout({}, ws, we)
    assert done is False and q is None
    assert ev.startswith("verifier error: db gone")


def test_missing_vault_fails_open_not_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(verifiers, "VAULT_ROOT", tmp_path / "nonexistent-vault")
    ws, we = day_window(WED)
    assert verifiers.vault_poem({}, ws, we)[0] is False
    assert verifiers.vault_roamings({}, ws, we)[0] is False
    assert verifiers.daily_note_reading({}, ws, we)[0] is False


# ---------------------------------------------------------------- auto_verify

class FakeQuery:
    """Minimal supabase-py query chain double."""

    def __init__(self, data=None):
        self._data = data or []
        self.inserted = None
        self.updated = None

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def execute(self): return MagicMock(data=self._data)
    def insert(self, record): self.inserted = record; return self
    def update(self, record): self.updated = record; return self


def make_client(tasks, completions):
    client = MagicMock()
    queries = {"tasks": FakeQuery(tasks), "task_completions": FakeQuery(completions)}
    client.table.side_effect = lambda name: queries[name]
    return client, queries["tasks"], queries["task_completions"]


def make_task(**overrides):
    task = {
        "id": 1,
        "title": "Go work out",
        "category": "physical",
        "priority": 5,
        "is_active": True,
        "is_recurring": True,
        "recurrence_pattern": "daily",
        "due_date": "2026-08-01T23:59:00+00:00",
        "verification": {"verifier": "whoop_workout"},
    }
    task.update(overrides)
    return task


ON_DATE = date(2026, 8, 1)


def test_period_window_daily_and_weekly():
    ws, we = auto_verify.period_window(make_task(recurrence_pattern="daily", due_date=None), ON_DATE)
    assert (ws, we) == day_window(ON_DATE)
    ws, we = auto_verify.period_window(make_task(recurrence_pattern="weekly", due_date=None), ON_DATE)
    assert ws.date() == date(2026, 7, 27)  # Monday
    assert we.date() == date(2026, 8, 2)   # Sunday


def test_period_window_respects_due_date():
    # overdue: due before on_date -> window anchors on the due date's period
    ws, we = auto_verify.period_window(make_task(due_date="2026-07-30T12:00:00+00:00"), ON_DATE)
    assert ws.date() == date(2026, 7, 30) and we.date() == date(2026, 7, 30)
    # future due beyond the window end -> window unchanged
    ws, we = auto_verify.period_window(make_task(due_date="2026-09-28T04:59:00+00:00"), ON_DATE)
    assert ws.date() == ON_DATE and we.date() == ON_DATE


def test_dry_run_idempotent_skip_when_already_completed():
    client, tasks_q, comps_q = make_client([make_task()], completions=[{"id": 99}])
    results = auto_verify.run(client, ON_DATE, dry_run=True)
    assert results[0]["status"] == "skipped"
    assert "already completed" in results[0]["detail"]
    assert comps_q.inserted is None and tasks_q.updated is None


def test_already_completed_window_bounds():
    ws, we = day_window(ON_DATE)  # daily window
    filters = {}

    class BoundQuery(FakeQuery):
        def gte(self, col, val):
            filters["gte"] = (col, val)
            return self

        def lte(self, col, val):
            filters["lte"] = (col, val)
            return self

    client = MagicMock()
    q = BoundQuery([{"id": 1}])
    client.table.side_effect = lambda name: q

    # a completion row inside the window -> covered
    assert auto_verify.already_completed(client, 1, ws, we) is True
    # no completion rows -> not covered
    q._data = []
    assert auto_verify.already_completed(client, 1, ws, we) is False
    # completed_at is bounded on both sides: window start .. window end + 1 period
    assert filters["gte"][0] == "completed_at"
    assert filters["gte"][1] == ws.astimezone().isoformat()
    assert filters["lte"][0] == "completed_at"
    assert filters["lte"][1] == (we + (we - ws)).astimezone().isoformat()


def test_dry_run_would_complete_but_writes_nothing(monkeypatch, capsys):
    monkeypatch.setitem(VERIFIERS, "whoop_workout", lambda t, a, b: (True, 4, "workout 45 min, strain 7.0"))
    client, tasks_q, comps_q = make_client([make_task()], completions=[])
    results = auto_verify.run(client, ON_DATE, dry_run=True)
    assert results[0]["status"] == "would_complete"
    assert results[0]["quality"] == 4
    assert comps_q.inserted is None and tasks_q.updated is None

    auto_verify.print_digest(results, ON_DATE, dry_run=True)
    out = capsys.readouterr().out
    assert "✅ Go work out (q4) — workout 45 min, strain 7.0" in out
    assert "1 completion(s) would be recorded." in out


def test_real_run_inserts_and_advances_due_date(monkeypatch):
    monkeypatch.setitem(VERIFIERS, "whoop_workout", lambda t, a, b: (True, 4, "workout 45 min"))
    task = make_task()
    client, tasks_q, comps_q = make_client([task], completions=[])
    results = auto_verify.run(client, ON_DATE, dry_run=False)

    assert results[0]["status"] == "completed"
    expected_points = main_module.calculate_points(task, 4, False)
    assert comps_q.inserted["points"] == expected_points
    assert comps_q.inserted["completion_quality"] == 4
    assert comps_q.inserted["was_late"] is False
    assert comps_q.inserted["notes"] == "auto: workout 45 min"
    # due date advanced by one daily interval: 2026-08-01 -> 2026-08-02
    assert tasks_q.updated["due_date"].startswith("2026-08-02")
    assert tasks_q.updated["is_active"] is True


def test_run_not_done_and_json_string_spec():
    client, _, comps_q = make_client(
        [make_task(verification='{"verifier": "manual"}')], completions=[]
    )
    results = auto_verify.run(client, ON_DATE, dry_run=True)
    assert results[0]["status"] == "not_done"
    assert results[0]["detail"] == "manual task"
    assert comps_q.inserted is None


def test_run_unknown_verifier_skipped():
    client, _, comps_q = make_client([make_task(verification={"verifier": "nope"})], completions=[])
    results = auto_verify.run(client, ON_DATE, dry_run=True)
    assert results[0]["status"] == "skipped"
    assert "unknown verifier" in results[0]["detail"]
    assert comps_q.inserted is None


def test_load_verifiable_tasks_filters():
    tasks = [
        make_task(id=1),
        make_task(id=2, verification=None),
        make_task(id=3, verification={}),
    ]
    client, _, _ = make_client(tasks, completions=[])
    loaded = auto_verify.load_verifiable_tasks(client)
    # client-side filter keeps only rows with a verifier name
    assert [t["id"] for t in loaded] == [1]
