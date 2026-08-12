-- Phase 2 Packet 2: private LangGraph checkpoint schema and deferred LightRAG capture.

CREATE SCHEMA IF NOT EXISTS langgraph;
CREATE SCHEMA IF NOT EXISTS lightrag;

COMMENT ON SCHEMA langgraph IS
  'LangGraph Postgres checkpointer tables (session/direct pool only). Packet 3 grants checkpointer role.';
COMMENT ON SCHEMA lightrag IS
  'Private LightRAG vendor storage. Full DDL deferred to Phase 5 initialize_storages capture.';

-- Reviewed placeholder matching langgraph-checkpoint-postgres MIGRATIONS (pinned LangGraph 1.2.x).
CREATE TABLE langgraph.checkpoint_migrations (
  v integer PRIMARY KEY
);

CREATE TABLE langgraph.checkpoints (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  parent_checkpoint_id text,
  type text,
  checkpoint jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE TABLE langgraph.checkpoint_blobs (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  channel text NOT NULL,
  version text NOT NULL,
  type text NOT NULL,
  blob bytea,
  PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);

CREATE TABLE langgraph.checkpoint_writes (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  task_id text NOT NULL,
  task_path text NOT NULL DEFAULT '',
  idx integer NOT NULL,
  channel text NOT NULL,
  type text,
  blob bytea NOT NULL,
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE INDEX checkpoints_thread_id_idx
  ON langgraph.checkpoints (thread_id);

CREATE INDEX checkpoint_blobs_thread_id_idx
  ON langgraph.checkpoint_blobs (thread_id);

CREATE INDEX checkpoint_writes_thread_id_idx
  ON langgraph.checkpoint_writes (thread_id);

INSERT INTO langgraph.checkpoint_migrations (v)
VALUES (0), (1), (2), (3), (4), (5), (6), (7), (8)
ON CONFLICT (v) DO NOTHING;

-- LightRAG vendor tables are NOT hand-authored here. Phase 5 runs pinned
-- initialize_storages() in an isolated bootstrap job and converts the captured
-- DDL/grants into the canonical migration artifact.
CREATE TABLE lightrag.schema_capture_status (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  lightrag_version text,
  capture_status text NOT NULL DEFAULT 'deferred',
  notes text NOT NULL DEFAULT
    'Awaiting Phase 5 pinned LightRAG initialize_storages() schema capture.',
  captured_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

INSERT INTO lightrag.schema_capture_status (lightrag_version, capture_status)
VALUES ('deferred', 'deferred');
