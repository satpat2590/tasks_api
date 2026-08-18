-- Atma — Tag-sprawl guard (TOC Phase C)
-- Marks auto-created tags (created by _ensure_tag when the triage LLM names a
-- domain absent from the tree) so Gyani can review and consolidate them instead
-- of letting loose LLM signatures fragment the knowledge graph.
-- Idempotent: safe to re-run.

BEGIN;

ALTER TABLE tags ADD COLUMN IF NOT EXISTS auto_created BOOLEAN NOT NULL DEFAULT FALSE;

COMMIT;
