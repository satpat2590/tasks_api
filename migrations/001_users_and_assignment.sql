-- Atma — Users table + agent assignment
-- Run in Supabase SQL Editor. Safe to re-run (IF NOT EXISTS).

BEGIN;

-- ── 1. Users table ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS users (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    user_type   TEXT NOT NULL DEFAULT 'human' CHECK (user_type IN ('human', 'agent')),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Seed initial users (idempotent)
INSERT INTO users (name, user_type) VALUES
    ('Satyam',   'human'),
    ('Argus',    'agent'),
    ('Veltiosi', 'agent'),
    ('Satya',    'agent')
ON CONFLICT (name) DO NOTHING;

-- ── 2. Add assignment columns to tasks ─────────────────────────

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS assigned_to INTEGER REFERENCES users(id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS created_by  INTEGER REFERENCES users(id);

-- Backfill existing tasks to Satyam (id=1) so nothing becomes orphaned
UPDATE tasks SET created_by = 1  WHERE created_by IS NULL;
UPDATE tasks SET assigned_to = 1 WHERE assigned_to IS NULL;

-- ── 3. Index for agent-scoped queries ──────────────────────────

CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by  ON tasks(created_by);

-- ── 4. View for easy agent task lookup ─────────────────────────

CREATE OR REPLACE VIEW agent_task_queue AS
SELECT
    t.id,
    t.title,
    t.category,
    t.priority,
    t.is_active,
    t.due_date,
    t.assigned_to,
    u.name AS assigned_to_name,
    u.user_type AS assigned_to_type,
    t.created_by,
    cu.name AS created_by_name
FROM tasks t
JOIN users u  ON t.assigned_to = u.id
JOIN users cu ON t.created_by  = cu.id
WHERE t.is_active = true
ORDER BY t.priority DESC, t.created_at DESC;

COMMIT;

-- ── Verification ───────────────────────────────────────────────

-- Check users were seeded:
-- SELECT * FROM users;

-- Check columns exist:
-- SELECT column_name, data_type FROM information_schema.columns 
--   WHERE table_name = 'tasks' AND column_name IN ('assigned_to', 'created_by');

-- Check the view:
-- SELECT * FROM agent_task_queue LIMIT 5;
