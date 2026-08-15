-- Atma — Delegation audit log (Task Ownership Classification, Phase 4)
-- Records every learn/delegate routing decision as an auditable trail.
-- Idempotent: safe to re-run.

BEGIN;

CREATE TABLE IF NOT EXISTS task_delegations (
    id              SERIAL PRIMARY KEY,
    task_id         INTEGER REFERENCES tasks(id),
    from_user       INTEGER REFERENCES users(id),   -- Satyam (orchestrator)
    to_user         INTEGER REFERENCES users(id),   -- the agent
    routing_decision VARCHAR NOT NULL,              -- 'learn' | 'delegate'
    rationale       TEXT,
    kanban_task_id  TEXT,                           -- handoff ref into the omni board
    state           VARCHAR DEFAULT 'delegated',    -- delegated | accepted | completed | rejected
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_task_delegations_task ON task_delegations(task_id);
CREATE INDEX IF NOT EXISTS idx_task_delegations_to   ON task_delegations(to_user);

COMMIT;
