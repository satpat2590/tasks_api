# SPEC — Atma Auto-Tagging: Restore, Fix, Backfill

Author: Satya (orchestrator) · For: OpenCode (kimi-k3) · Date: 2026-07-24

## Background

Atma (`~/atma`) is the task manager. Its `create_task` endpoint (`~/atma/main.py:498`)
calls `auto_tag_task()` (`~/atma/utils/tags.py`) which asks an LLM to assign
hierarchical tags to each new task, creating tag rows (`tags` table, parent_tag_id
chains) and linking rows (`task_tags` join table). This powers the Omni mindmap:
points roll up the tag tree and show domains/fields of experience.

**Current state: broken.**
1. Model ID `claude-sonnet-4-20250514` in tags.py:97 is deprecated — calls fail,
   task creation logs `[WARN] Auto-tagging failed` and continues untagged.
2. Single-provider (Anthropic only) with no fallback.
3. 22 of 33 existing tasks have NO tags (all Edoras agent tasks + several personal).
4. `tags.py` is sync-blocking inside an async endpoint.

## Requirements (acceptance criteria)

### R1 — Working auto-tagging on task creation
- `POST /api/tasks` auto-tags every new task (already wired — just needs to WORK).
- LLM provider: **kimi-k3 via OpenRouter** (OpenAI-compatible API,
  `https://openrouter.ai/api/v1`, model `moonshotai/kimi-k3`,
  key from `OPENROUTER_API_KEY` env — already in environment).
  Do NOT keep Anthropic as primary.
- Fail-open preserved: tagging failure must NEVER fail task creation
  (current try/except pattern is correct — keep it).
- Tagging must be non-blocking for the HTTP response: run as an
  `asyncio.create_task` background job OR keep inline with a hard 15s timeout.
  (Choose background task; log outcome.)

### R2 — Provider fallback chain
- Order: OpenRouter kimi-k3 → DeepSeek (`deepseek-chat`, `DEEPSEEK_API_KEY` env)
  → Anthropic (`claude-sonnet-4-5`, `ANTHROPIC_API_KEY` env).
- Try each in order on exception or empty result; log which provider succeeded.
- Parse robustly: LLM may return JSON array, JSON with preamble, or bullet list.
  Accept `["A/B/C", ...]` paths; strip markdown fences.

### R3 — Backfill script for untagged tasks
- New script `~/atma/scripts/backfill_tags.py`:
  - Finds ALL tasks (all users, all categories) with zero rows in task_tags.
  - Tags each via the same R1/R2 pipeline (shared module, not copy-paste).
  - Rate-limited: 1 request / 1.5s, progress printed every task, resumable
    (skips tasks that already have tags on re-run).
  - `--dry-run` flag prints what would be tagged without writing.
- Expected scope (verify at runtime): ~22 tasks across users incl. all
  edoras-category agent tasks.

### R4 — Mindmap integrity (verification, no code change)
- The Omni mindmap (`~/omni/mindmap.py`) already filters to Satyam-only tasks
  (verified working). Backfill tags agent tasks too — that's correct, they
  belong in the tag tree for future per-agent maps, but the personal mindmap
  must remain Satyam-only. After backfill, run `python3 ~/omni/mindmap.py`
  and confirm the stats line still shows Satyam-only task count (currently 11).

### R5 — Tests
- `~/atma/tests/test_auto_tag.py`:
  - Mock LLM responses for each provider; verify fallback order.
  - Verify `ensure_tag_exists` reuses existing tags (no duplicates) and
    creates missing hierarchy levels with correct parent_tag_id.
  - Verify fail-open: all providers raising → task creation still succeeds.
  - Run: `cd ~/atma && python3 -m pytest tests/test_auto_tag.py -v` — all pass.

### R6 — Don't break things
- `cd ~/atma && python3 -m pytest tests/ -q` — full suite passes.
- `python3 -c "from main import app"` imports clean.
- No changes to the tags table schema. No changes to mindmap.py.

## Repo facts (verified by orchestrator)
- `~/atma/main.py:498` create_task; tags.py imported at main.py:28.
- `~/atma/utils/tags.py`: auto_tag_task, ensure_tag_exists, build_hierarchy_string.
- Supabase via env: SUPABASE_URL, SUPABASE_KEY (or SUPABASE_API_KEY).
- tags table: id, name, parent_tag_id, category. task_tags: task_id, tag_id.
- Edoras tasks exist under categories 'edoras', 'mental', etc. — backfill
  uses the task's OWN category for its tag tree.
- Existing tests live in ~/atma/tests/ (create dir if missing).

## Deliverables
1. Modified `~/atma/utils/tags.py` (provider chain, robust parsing).
2. Modified `~/atma/main.py` (background tagging task, timeout).
3. New `~/atma/scripts/backfill_tags.py`.
4. New `~/atma/tests/test_auto_tag.py`.
5. Verification report: tests passing, dry-run backfill output, real backfill
   output (task count + tag count before/after), mindmap rebuild stats.
