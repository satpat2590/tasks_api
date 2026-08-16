-- Atma — Agent expertise + self-assessment signal (TOC Phase B)
-- Two new primitives:
--   agent_domains    — "configured" expertise: the root tags an agent is
--                      DECLARED to own (their whole subtree is padded out).
--   self_assessments — a non-fungible record of Satyam's routing decisions,
--                      capturing the act of *recognizing* a capability gap.
--                      Never awards work-credit (separate from growth points).
-- Idempotent: safe to re-run.

BEGIN;

-- ── 1. Configured agent domains ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS agent_domains (
    agent_id  INTEGER REFERENCES users(id),
    tag_id    INTEGER REFERENCES tags(id),   -- a ROOT tag; subtree = configured
    PRIMARY KEY (agent_id, tag_id)
);

-- Seed configured baselines. Paisa/Argus → Finance (and Paisa → ML), Satya →
-- Mathematics (philosophy-adjacent), Veltiosi → Computer Science (knowledge
-- infra). Adjustable; "demonstrated" expertise layers on top from real work.
INSERT INTO agent_domains (agent_id, tag_id) VALUES
    (5, 90),   -- Paisa → Finance
    (5, 10),   -- Paisa → Machine Learning
    (2, 90),   -- Argus → Finance
    (4, 30),   -- Satya → Mathematics
    (3, 60)    -- Veltiosi → Computer Science
ON CONFLICT (agent_id, tag_id) DO NOTHING;

-- ── 2. Self-assessment signal ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS self_assessments (
    id                SERIAL PRIMARY KEY,
    task_id           INTEGER REFERENCES tasks(id),
    decision          VARCHAR NOT NULL,      -- 'learn' | 'delegate'
    had_gap           BOOLEAN NOT NULL,      -- was there a capability gap?
    gap_tags          JSONB,                 -- ["Finance — Risk Management", …]
    gap_magnitude     REAL,                  -- sum of gaps across signature tags
    recommended_agent VARCHAR,               -- triage's suggestion (nullable)
    chosen_agent      VARCHAR,               -- agent picked (delegate only)
    created_at        TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_self_assessments_created ON self_assessments(created_at);

COMMIT;
