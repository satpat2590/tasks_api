#!/usr/bin/env python3
"""Nightly auto-verification job for Atma growth tasks (SPEC §3).

For every active recurring task with a `verification` spec, look for evidence
in the task's current period window and, if found (and the period is not
already completed), record the completion and advance the recurrence.

Usage:
    python3 ~/atma/scripts/auto_verify.py [--dry-run] [--date YYYY-MM-DD]
"""

import argparse
import json
import os
import sys
from datetime import date, datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from supabase import Client, create_client  # noqa: E402

# Reuse the existing completion rules — import, don't copy.
import main as main_module  # noqa: E402
from utils.verifiers import VERIFIERS  # noqa: E402


def get_client() -> Client:
    """Supabase client, same pattern as main.py."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY") or os.getenv("SUPABASE_API_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_KEY or SUPABASE_API_KEY must be set")
    return create_client(url, key)


def verification_spec(task):
    """Parsed verification dict for a task row, or None."""
    spec = task.get("verification")
    if isinstance(spec, str):
        try:
            spec = json.loads(spec)
        except ValueError:
            return None
    if isinstance(spec, dict) and spec.get("verifier"):
        return spec
    return None


def load_verifiable_tasks(client):
    """Active recurring tasks where verification->>'verifier' is not null."""
    resp = client.table("tasks").select("*").eq("is_active", True).eq("is_recurring", True).execute()
    return [t for t in (resp.data or []) if verification_spec(t)]


def period_window(task, on_date):
    """Current period window for a task as naive local datetimes.

    daily: that calendar day; weekly: Mon-Sun containing the date. The task's
    due_date is respected as the period end; if the task is overdue relative
    to on_date, the window anchors on the due date's period instead.
    """
    pattern = (task.get("recurrence_pattern") or "").strip().lower()
    due = main_module.parse_datetime(task.get("due_date"))
    due_day = due.astimezone().date() if due else None

    anchor = on_date
    if due_day and due_day < on_date:
        anchor = due_day

    if pattern == "weekly":
        monday = anchor - timedelta(days=anchor.weekday())
        start = datetime.combine(monday, time.min)
        end = datetime.combine(monday + timedelta(days=6), time.max)
    else:  # daily (default) and any other pattern: single-day window
        start = datetime.combine(anchor, time.min)
        end = datetime.combine(anchor, time.max)

    if due_day:
        due_end = datetime.combine(due_day, time.max)
        if due_end < end:
            end = due_end
    return start, end


def already_completed(client, task_id, window_start, window_end):
    """True if a completion for this task already covers this period.

    A completion counts if it landed within the window or within one period
    after it (the SPEC's late-grace window) — so post-midnight auto-completions
    still idempotently block re-runs for the period they verified.
    """
    grace_end = window_end + (window_end - window_start)
    resp = (
        client.table("task_completions")
        .select("id")
        .eq("task_id", task_id)
        .gte("completed_at", window_start.astimezone().isoformat())
        .lte("completed_at", grace_end.astimezone().isoformat())
        .limit(1)
        .execute()
    )
    return bool(resp.data)


def run(client, on_date, dry_run=False):
    """Verify all eligible tasks for the period containing on_date."""
    results = []
    for task in load_verifiable_tasks(client):
        verifier_name = verification_spec(task)["verifier"]
        verifier = VERIFIERS.get(verifier_name)
        if verifier is None:
            results.append({"task": task, "status": "skipped", "detail": f"unknown verifier '{verifier_name}'"})
            continue

        window_start, window_end = period_window(task, on_date)
        if already_completed(client, task["id"], window_start, window_end):
            results.append({"task": task, "status": "skipped", "detail": "already completed this period"})
            continue

        done, quality, evidence = verifier(task, window_start, window_end)
        if not done:
            results.append({"task": task, "status": "not_done", "detail": evidence})
            continue

        quality = quality if quality is not None else 3
        points = main_module.calculate_points(task, quality, False)
        status = "would_complete" if dry_run else "completed"

        if not dry_run:
            now = datetime.now(timezone.utc)
            client.table("task_completions").insert(
                {
                    "task_id": task["id"],
                    "completed_at": now.isoformat(),
                    "completion_quality": quality,
                    "notes": f"auto: {evidence}",
                    "was_late": False,
                    "time_spent_minutes": 0,
                    "points": points,
                }
            ).execute()
            due = main_module.parse_datetime(task.get("due_date"))
            next_due = main_module.calculate_next_due_date(due or now, task.get("recurrence_pattern"))
            client.table("tasks").update(
                {"due_date": next_due.isoformat(), "is_active": True}
            ).eq("id", task["id"]).execute()

        results.append(
            {"task": task, "status": status, "detail": evidence, "quality": quality, "points": points}
        )
    return results


def print_digest(results, on_date, dry_run=False):
    mode = "[dry-run] " if dry_run else ""
    print(f"{mode}auto-verify digest for {on_date.isoformat()}")
    completions = 0
    for r in results:
        title = r["task"].get("title", f"task {r['task'].get('id')}")
        if r["status"] in ("completed", "would_complete"):
            completions += 1
            print(f"✅ {title} (q{r['quality']}) — {r['detail']}")
        elif r["status"] == "skipped":
            print(f"skip: {title} — {r['detail']}")
        else:
            print(f"miss: {title} — {r['detail']}")
    verb = "would be recorded" if dry_run else "recorded"
    print(f"{completions} completion(s) {verb}.")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Auto-verify recurring growth tasks.")
    parser.add_argument("--dry-run", action="store_true", help="print what would complete; write nothing")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="period date, YYYY-MM-DD (default: today)",
    )
    args = parser.parse_args(argv)

    client = get_client()
    results = run(client, args.date, dry_run=args.dry_run)
    print_digest(results, args.date, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
