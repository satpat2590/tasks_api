-- Atma — Delegation completion tracking (TOC Phase A)
-- Adds completed_at to task_delegations so the agent-completion sync can
-- record when a delegated task was actually finished (feeds accountability
-- and, later, per-agent expertise tracking).
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE task_delegations ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_task_delegations_state ON task_delegations(state);

COMMIT;
