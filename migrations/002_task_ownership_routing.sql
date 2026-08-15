-- Atma — Task Ownership Routing (TOC)
-- Adds agent users, the Finance domain, per-task skill signatures, and
-- ownership-routing columns. This is the data foundation for Gyani's
-- "can Satyam do this, or does it route to an agent?" triage.
--
-- Idempotent: safe to re-run. Run in Supabase SQL Editor or via psql.

BEGIN;

-- ── 1. Register missing agents ────────────────────────────────────────────
-- Stable, well-known ids so the triage endpoint can route by agent id.
INSERT INTO users (id, name, user_type) VALUES
    (5, 'Paisa',  'agent'),
    (6, 'Gyani',  'agent')
ON CONFLICT (name) DO NOTHING;

SELECT setval('users_id_seq', GREATEST((SELECT MAX(id) FROM users), 6));

-- ── 2. Finance tag subtree ────────────────────────────────────────────────
-- Root + five children. Idempotent on the unique name.
INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 90, 'Finance', NULL, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance');

INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 91, 'Finance — Fundamentals', 90, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance — Fundamentals');

INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 92, 'Finance — Markets', 90, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance — Markets');

INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 93, 'Finance — Quantitative', 90, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance — Quantitative');

INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 94, 'Finance — Risk Management', 93, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance — Risk Management');

INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 95, 'Finance — Crypto', 92, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance — Crypto');

INSERT INTO tags (id, name, parent_tag_id, category, required_proficiency, created_at)
SELECT 96, 'Finance — Market Sentiment', 92, 'financial', 3.0, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tags WHERE name = 'Finance — Market Sentiment');

SELECT setval('tags_id_seq', GREATEST((SELECT MAX(id) FROM tags), 96));

-- ── 3. Cross-domain convergence gates ─────────────────────────────────────
-- Finance — Quantitative needs Mathematics AND Probability & Statistics.
-- Risk Management sits on top of Quantitative. Crypto and Sentiment sit on
-- Markets (Sentiment also pulls in Statistics + ML).
INSERT INTO tag_dependencies (tag_id, depends_on_tag_id, required_proficiency) VALUES
    (93, 30, 2.5),   -- Finance — Quantitative      ← Mathematics
    (93, 13, 2.5),   -- Finance — Quantitative      ← Probability & Statistics
    (94, 93, 2.0),   -- Finance — Risk Management   ← Finance — Quantitative
    (95, 92, 2.0),   -- Finance — Crypto            ← Finance — Markets
    (96, 13, 2.0),   -- Finance — Market Sentiment  ← Probability & Statistics
    (96, 10, 2.0)    -- Finance — Market Sentiment  ← Machine Learning
ON CONFLICT (tag_id, depends_on_tag_id) DO NOTHING;

-- ── 4. Root Finance task ──────────────────────────────────────────────────
-- CRITICAL invariant: a root tag with zero tasks can never accrue proficiency,
-- so every child stays locked forever. One gentle conceptual intro task.
INSERT INTO tasks (title, category, priority, description, assigned_to, created_by, is_active, created_at)
SELECT 'Explain what makes Finance unique as a discipline', 'financial', 3,
       'A gentle conceptual introduction to finance: what it measures, why it exists, and how it differs from pure mathematics and economics.',
       1, 1, TRUE, NOW()
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title = 'Explain what makes Finance unique as a discipline');

INSERT INTO task_tags (task_id, tag_id)
SELECT t.id, 90 FROM tasks t
WHERE t.title = 'Explain what makes Finance unique as a discipline'
  AND NOT EXISTS (SELECT 1 FROM task_tags tt WHERE tt.task_id = t.id AND tt.tag_id = 90);

-- ── 5. Per-task skill signature ───────────────────────────────────────────
-- What tags (and at what proficiency) a task requires. Gyani's triage diffs
-- this against Satyam's ledger proficiency to produce a gap vector.
CREATE TABLE IF NOT EXISTS task_skill_requirements (
    task_id               INTEGER REFERENCES tasks(id),
    tag_id                INTEGER REFERENCES tags(id),
    required_proficiency  REAL DEFAULT 3.0,
    PRIMARY KEY (task_id, tag_id)
);

-- ── 6. Ownership routing columns on tasks ─────────────────────────────────
-- owner_type    'satyam' | 'agent' — who the task ultimately belongs to.
-- routing_state NULL (untriaged) | 'ready' (Satyam can do it) |
--               'learning_gap' (blocked on prerequisites) |
--               'delegated' (an agent is handling it) | 'triage_pending'
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS owner_type    VARCHAR DEFAULT 'satyam';
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS routing_state VARCHAR;

CREATE INDEX IF NOT EXISTS idx_tasks_routing_state ON tasks(routing_state);

COMMIT;

-- ── Verification ───────────────────────────────────────────────────────────
-- SELECT id, name, user_type FROM users ORDER BY id;
-- SELECT id, name, parent_tag_id, category FROM tags WHERE category = 'financial' ORDER BY id;
-- SELECT * FROM tag_dependencies WHERE tag_id BETWEEN 90 AND 96;
-- SELECT column_name FROM information_schema.columns
--   WHERE table_name = 'tasks' AND column_name IN ('owner_type', 'routing_state');
-- SELECT * FROM task_skill_requirements;
