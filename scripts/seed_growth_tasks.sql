-- seed_growth_tasks.sql — Growth system revamp (SPEC 2026-08-01 §3)
-- ⚠️  DO NOT RUN against prod without orchestrator review.
-- Attaches verifiers to existing recurring tasks and seeds the new growth tasks.
-- Idempotent: UPDATEs are plain; INSERTs are guarded by WHERE NOT EXISTS on title.

BEGIN;

-- ── 1. Attach verifiers to existing recurring tasks ─────────────────────────

UPDATE tasks SET verification = '{"verifier":"whoop_workout"}' WHERE id = 1;
UPDATE tasks SET verification = '{"verifier":"whoop_deficit"}' WHERE id = 2;
UPDATE tasks SET verification = '{"verifier":"vault_poem"}'    WHERE id = 6;

-- ── 2. Seed new growth tasks (assigned_to=1 Satyam, created_by=1, priority 3) ──

INSERT INTO tasks (title, description, category, priority, due_date,
                   is_recurring, recurrence_pattern, is_active, assigned_to, created_by, verification)
SELECT 'Satya''s Roamings — daily philosophical exploration',
       'Auto-verified: new note appears in Satya''s Roamings/',
       'mental', 3, (CURRENT_DATE + 1)::timestamptz,
       TRUE, 'daily', TRUE, 1, 1, '{"verifier":"vault_roamings"}'
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title = 'Satya''s Roamings — daily philosophical exploration');

INSERT INTO tasks (title, description, category, priority, due_date,
                   is_recurring, recurrence_pattern, is_active, assigned_to, created_by, verification)
SELECT 'Read/research 30 minutes',
       'Auto-verified: daily note has a Reading/Research section or a new wikilink',
       'mental', 3, (CURRENT_DATE + 1)::timestamptz,
       TRUE, 'daily', TRUE, 1, 1, '{"verifier":"daily_note_reading"}'
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title = 'Read/research 30 minutes');

INSERT INTO tasks (title, description, category, priority, due_date,
                   is_recurring, recurrence_pattern, is_active, assigned_to, created_by, verification)
SELECT 'Ship one thing',
       'Auto-verified: >=1 commit by Satyam across edoras/omni/atma/Obsidian',
       'financial', 3, (date_trunc('week', CURRENT_DATE)::date + 6)::timestamptz, -- Sunday
       TRUE, 'weekly', TRUE, 1, 1, '{"verifier":"git_ship"}'
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title = 'Ship one thing');

INSERT INTO tasks (title, description, category, priority, due_date,
                   is_recurring, recurrence_pattern, is_active, assigned_to, created_by, verification)
SELECT 'Call family',
       'Manual completion only',
       'social', 3, (date_trunc('week', CURRENT_DATE)::date + 6)::timestamptz, -- Sunday
       TRUE, 'weekly', TRUE, 1, 1, '{"verifier":"manual"}'
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title = 'Call family');

INSERT INTO tasks (title, description, category, priority, due_date,
                   is_recurring, recurrence_pattern, is_active, assigned_to, created_by, verification)
SELECT 'Plan the week',
       'Manual completion only; due Mondays',
       'mental', 3, (date_trunc('week', CURRENT_DATE)::date + 7)::timestamptz, -- next Monday
       TRUE, 'weekly', TRUE, 1, 1, '{"verifier":"manual"}'
WHERE NOT EXISTS (SELECT 1 FROM tasks WHERE title = 'Plan the week');

COMMIT;
