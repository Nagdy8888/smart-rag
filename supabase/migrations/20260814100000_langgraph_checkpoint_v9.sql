-- Phase 3 gap close-out Run 1: record langgraph-checkpoint-postgres 3.1.2
-- migration 9. The task_path column already exists from
-- 20260812135111_langgraph_lightrag_private_v1.sql. Runtime must never call
-- PostgresSaver.setup(); this INSERT only aligns checkpoint_migrations with
-- the pinned library MIGRATIONS list (indices 0-9).

INSERT INTO langgraph.checkpoint_migrations (v)
VALUES (9)
ON CONFLICT (v) DO NOTHING;

COMMENT ON TABLE langgraph.checkpoint_migrations IS
  'Pinned langgraph-checkpoint-postgres 3.1.2 schema versions (0-9). Runtime does not auto-migrate.';
