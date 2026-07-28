#!/usr/bin/env python3
"""
Backfill tags for untagged tasks (SPEC-autotag.md, requirement R3).

Finds ALL tasks (all users, all categories) with zero rows in task_tags,
tags each via utils.tags.auto_tag_task (the shared R1/R2 pipeline), and
inserts the resulting rows into task_tags.

- Rate-limited: 1.5s between LLM calls (i.e. between tasks).
- Progress printed for every task.
- Resumable: re-running skips tasks that already have tags.
- --dry-run: print what would be tagged without any LLM calls or writes.
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Make the repo root importable so `utils.tags` resolves when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Shared module (NOT copy-paste): reuses the same supabase client, built from
# SUPABASE_URL + SUPABASE_KEY/SUPABASE_API_KEY env vars in utils/tags.py
from utils.tags import auto_tag_task, supabase

RATE_LIMIT_SECONDS = 1.5


def find_untagged_tasks():
    """Return all tasks (any user, any category) with zero rows in task_tags."""
    tasks = supabase.table("tasks").select("*").execute().data or []
    task_tag_rows = supabase.table("task_tags").select("task_id").execute().data or []
    tagged_task_ids = {row["task_id"] for row in task_tag_rows}
    return [task for task in tasks if task["id"] not in tagged_task_ids]


async def backfill(dry_run: bool = False):
    untagged = find_untagged_tasks()
    total = len(untagged)
    print(f"Found {total} untagged task(s).")

    if total == 0:
        print("Nothing to do.")
        return

    tagged_count = 0
    failed_count = 0

    for index, task in enumerate(untagged, start=1):
        print(
            f"[{index}/{total}] Task id={task['id']} "
            f"category={task.get('category')!r} title={task.get('title')!r}"
        )

        if dry_run:
            print(f"  [DRY-RUN] Would auto-tag task {task['id']} and insert task_tags rows.")
            continue

        try:
            tag_ids = await auto_tag_task(task)
            if not tag_ids:
                print(f"  [WARN] auto_tag_task returned no tags for task {task['id']}; skipping.")
                failed_count += 1
            else:
                # Dedupe: task_tags has PRIMARY KEY (task_id, tag_id)
                for tag_id in dict.fromkeys(tag_ids):
                    supabase.table("task_tags").insert({
                        "task_id": task["id"],
                        "tag_id": tag_id,
                    }).execute()
                print(f"  Tagged task {task['id']} with {len(set(tag_ids))} tag(s): {sorted(set(tag_ids))}")
                tagged_count += 1
        except Exception as e:
            print(f"  [ERROR] Failed to tag task {task['id']}: {e}")
            failed_count += 1

        # Rate limit: 1.5s between LLM calls (skip the sleep after the last task)
        if index < total:
            await asyncio.sleep(RATE_LIMIT_SECONDS)

    if dry_run:
        print(f"\n[DRY-RUN] Would tag {total} task(s). No LLM calls made, no rows written.")
    else:
        print(f"\nDone. Tagged {tagged_count} task(s), {failed_count} failed/untagged.")


async def main():
    parser = argparse.ArgumentParser(
        description="Backfill tags for tasks with zero rows in task_tags (SPEC-autotag R3)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be tagged without any LLM calls or writes.",
    )
    args = parser.parse_args()
    await backfill(dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
