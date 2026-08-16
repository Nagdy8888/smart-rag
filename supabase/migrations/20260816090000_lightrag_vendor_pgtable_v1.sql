-- Phase 5 Packet 2: reviewed LightRAG 1.5.6 PGTableGraphStorage vendor schema.
-- Source (not retyped from memory):
--   lightrag.kg.pgtable_impl.PGTableGraphStorage._DDL (steady-state CREATE/INDEX/FK)
--   lightrag.kg.postgres_impl.TABLES (KV / doc-status / full-entities)
--   PGVectorStorage.setup_table / _pg_create_table / _safe_index_name
--     for text-embedding-3-large @ 1024 (suffix text_embedding_3_large_1024d)
--   PostgreSQLDB.check_tables index names, pagination indexes, scheduling index
-- Legacy ALTER/DROP PK paths from vendor _DDL are omitted (expand-only release).
-- Search path during vendor init: lightrag,extensions,public.

-- ---------------------------------------------------------------------------
-- Graph tables (PGTableGraphStorage._DDL steady state)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lightrag.lightrag_graph_nodes (
  workspace text NOT NULL,
  namespace text NOT NULL DEFAULT 'chunk_entity_relation',
  id text NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace, namespace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_graph_edges (
  workspace text NOT NULL,
  namespace text NOT NULL DEFAULT 'chunk_entity_relation',
  src_id text NOT NULL,
  tgt_id text NOT NULL,
  properties jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (workspace, namespace, src_id, tgt_id)
);

CREATE INDEX IF NOT EXISTS idx_lightrag_graph_edges_namespace_tgt
  ON lightrag.lightrag_graph_edges (workspace, namespace, tgt_id);

CREATE INDEX IF NOT EXISTS idx_lightrag_graph_edges_noncanonical
  ON lightrag.lightrag_graph_edges (workspace, namespace)
  WHERE src_id COLLATE "C" > tgt_id COLLATE "C";

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_lightrag_graph_edges_src'
      AND conrelid = 'lightrag.lightrag_graph_edges'::regclass
  ) THEN
    ALTER TABLE lightrag.lightrag_graph_edges
      ADD CONSTRAINT fk_lightrag_graph_edges_src
      FOREIGN KEY (workspace, namespace, src_id)
      REFERENCES lightrag.lightrag_graph_nodes (workspace, namespace, id)
      ON DELETE CASCADE;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_lightrag_graph_edges_tgt'
      AND conrelid = 'lightrag.lightrag_graph_edges'::regclass
  ) THEN
    ALTER TABLE lightrag.lightrag_graph_edges
      ADD CONSTRAINT fk_lightrag_graph_edges_tgt
      FOREIGN KEY (workspace, namespace, tgt_id)
      REFERENCES lightrag.lightrag_graph_nodes (workspace, namespace, id)
      ON DELETE CASCADE;
  END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- KV / doc-status / entity-chunk tables (postgres_impl.TABLES)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lightrag.lightrag_doc_full (
  id varchar(255),
  workspace varchar(255),
  doc_name varchar(1024),
  content text,
  meta jsonb,
  sidecar_location text NULL,
  parse_format varchar(32) NULL DEFAULT 'raw',
  content_hash text NULL,
  process_options text NULL,
  chunk_options jsonb NULL DEFAULT '{}'::jsonb,
  parse_engine text NULL,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_doc_full_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_doc_chunks (
  id varchar(255),
  workspace varchar(255),
  full_doc_id varchar(256),
  chunk_order_index integer,
  tokens integer,
  content text,
  file_path text NULL,
  llm_cache_list jsonb NULL DEFAULT '[]'::jsonb,
  heading jsonb NULL DEFAULT '{}'::jsonb,
  sidecar jsonb NULL DEFAULT '{}'::jsonb,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_doc_chunks_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_llm_cache (
  workspace varchar(255) NOT NULL,
  id varchar(255) NOT NULL,
  original_prompt text,
  return_value text,
  chunk_id varchar(255) NULL,
  cache_type varchar(32),
  queryparam jsonb NULL,
  create_time timestamp DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_llm_cache_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_doc_status (
  workspace varchar(255) NOT NULL,
  id varchar(255) NOT NULL,
  content_summary varchar(255) NULL,
  content_length integer NULL,
  chunks_count integer NULL,
  status varchar(64) NULL,
  file_path text NULL,
  chunks_list jsonb NULL DEFAULT '[]'::jsonb,
  track_id varchar(255) NULL,
  metadata jsonb NULL DEFAULT '{}'::jsonb,
  error_msg text NULL,
  content_hash text NULL,
  created_at timestamp DEFAULT CURRENT_TIMESTAMP,
  updated_at timestamp DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_doc_status_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_full_entities (
  id varchar(255),
  workspace varchar(255),
  entity_names jsonb,
  count integer,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_full_entities_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_full_relations (
  id varchar(255),
  workspace varchar(255),
  relation_pairs jsonb,
  count integer,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_full_relations_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_entity_chunks (
  id varchar(512),
  workspace varchar(255),
  chunk_ids jsonb,
  count integer,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_entity_chunks_pk PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_relation_chunks (
  id varchar(512),
  workspace varchar(255),
  chunk_ids jsonb,
  count integer,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_relation_chunks_pk PRIMARY KEY (workspace, id)
);

-- ---------------------------------------------------------------------------
-- Vector tables (setup_table for text-embedding-3-large @ 1024)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS lightrag.lightrag_vdb_chunks_text_embedding_3_large_1024d (
  id varchar(255),
  workspace varchar(255),
  full_doc_id varchar(256),
  chunk_order_index integer,
  tokens integer,
  content text,
  content_vector extensions.vector(1024),
  file_path text NULL,
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT lightrag_vdb_chunks_text_embedding_3_large_1024d_pk
    PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_vdb_entity_text_embedding_3_large_1024d (
  id varchar(255),
  workspace varchar(255),
  entity_name varchar(512),
  content text,
  content_vector extensions.vector(1024),
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  chunk_ids varchar(255)[] NULL,
  file_path text NULL,
  CONSTRAINT lightrag_vdb_entity_text_embedding_3_large_1024d_pk
    PRIMARY KEY (workspace, id)
);

CREATE TABLE IF NOT EXISTS lightrag.lightrag_vdb_relation_text_embedding_3_large_1024d (
  id varchar(255),
  workspace varchar(255),
  source_id varchar(512),
  target_id varchar(512),
  content text,
  content_vector extensions.vector(1024),
  create_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  update_time timestamp(0) DEFAULT CURRENT_TIMESTAMP,
  chunk_ids varchar(255)[] NULL,
  file_path text NULL,
  CONSTRAINT lightrag_vdb_relation_text_embedding_3_large_1024d_pk
    PRIMARY KEY (workspace, id)
);

-- ---------------------------------------------------------------------------
-- Vendor check_tables / pagination / scheduling / vector indexes
-- CREATE INDEX CONCURRENTLY is not used (migrations run in a transaction).
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_lightrag_doc_full_id
  ON lightrag.lightrag_doc_full (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_full_workspace_id
  ON lightrag.lightrag_doc_full (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_doc_chunks_id
  ON lightrag.lightrag_doc_chunks (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_chunks_workspace_id
  ON lightrag.lightrag_doc_chunks (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_llm_cache_id
  ON lightrag.lightrag_llm_cache (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_llm_cache_workspace_id
  ON lightrag.lightrag_llm_cache (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_id
  ON lightrag.lightrag_doc_status (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_workspace_id
  ON lightrag.lightrag_doc_status (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_full_entities_id
  ON lightrag.lightrag_full_entities (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_full_entities_workspace_id
  ON lightrag.lightrag_full_entities (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_full_relations_id
  ON lightrag.lightrag_full_relations (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_full_relations_workspace_id
  ON lightrag.lightrag_full_relations (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_entity_chunks_id
  ON lightrag.lightrag_entity_chunks (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_entity_chunks_workspace_id
  ON lightrag.lightrag_entity_chunks (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_relation_chunks_id
  ON lightrag.lightrag_relation_chunks (id);
CREATE INDEX IF NOT EXISTS idx_lightrag_relation_chunks_workspace_id
  ON lightrag.lightrag_relation_chunks (workspace, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_workspace_status_updated_at
  ON lightrag.lightrag_doc_status (workspace, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_workspace_status_created_at
  ON lightrag.lightrag_doc_status (workspace, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_workspace_updated_at
  ON lightrag.lightrag_doc_status (workspace, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_workspace_created_at
  ON lightrag.lightrag_doc_status (workspace, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_workspace_file_path
  ON lightrag.lightrag_doc_status (workspace, file_path);
CREATE INDEX IF NOT EXISTS idx_lightrag_doc_status_ws_status_created_nf_id
  ON lightrag.lightrag_doc_status (workspace, status, created_at NULLS FIRST, id);

CREATE INDEX IF NOT EXISTS idx_lightrag_vdb_chunks_text_embedding_3_large_1024d_id
  ON lightrag.lightrag_vdb_chunks_text_embedding_3_large_1024d (id);
CREATE INDEX IF NOT EXISTS idx_13c1a90d39e2_workspace_id
  ON lightrag.lightrag_vdb_chunks_text_embedding_3_large_1024d (workspace, id);
CREATE INDEX IF NOT EXISTS idx_13c1a90d39e2_hnsw_cosine
  ON lightrag.lightrag_vdb_chunks_text_embedding_3_large_1024d
  USING hnsw (content_vector extensions.vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_lightrag_vdb_entity_text_embedding_3_large_1024d_id
  ON lightrag.lightrag_vdb_entity_text_embedding_3_large_1024d (id);
CREATE INDEX IF NOT EXISTS idx_58a638caa9ec_workspace_id
  ON lightrag.lightrag_vdb_entity_text_embedding_3_large_1024d (workspace, id);
CREATE INDEX IF NOT EXISTS idx_58a638caa9ec_hnsw_cosine
  ON lightrag.lightrag_vdb_entity_text_embedding_3_large_1024d
  USING hnsw (content_vector extensions.vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_lightrag_vdb_relation_text_embedding_3_large_1024d_id
  ON lightrag.lightrag_vdb_relation_text_embedding_3_large_1024d (id);
CREATE INDEX IF NOT EXISTS idx_afd21a368d78_workspace_id
  ON lightrag.lightrag_vdb_relation_text_embedding_3_large_1024d (workspace, id);
CREATE INDEX IF NOT EXISTS idx_afd21a368d78_hnsw_cosine
  ON lightrag.lightrag_vdb_relation_text_embedding_3_large_1024d
  USING hnsw (content_vector extensions.vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- Capture-status expand (no DROP) + pin record
-- ---------------------------------------------------------------------------

ALTER TABLE lightrag.schema_capture_status
  ADD COLUMN IF NOT EXISTS pin_commit text;

ALTER TABLE lightrag.schema_capture_status
  ADD COLUMN IF NOT EXISTS embedding_model text;

ALTER TABLE lightrag.schema_capture_status
  ADD COLUMN IF NOT EXISTS embedding_dimensions integer;

ALTER TABLE lightrag.schema_capture_status
  ADD COLUMN IF NOT EXISTS fingerprint_sha256 text;

ALTER TABLE lightrag.schema_capture_status
  ADD COLUMN IF NOT EXISTS search_path text;

ALTER TABLE lightrag.schema_capture_status
  ADD COLUMN IF NOT EXISTS warning_report jsonb NOT NULL DEFAULT '[]'::jsonb;

UPDATE lightrag.schema_capture_status
SET
  lightrag_version = '1.5.6',
  capture_status = 'captured',
  pin_commit = 'b33c6b0812cddf39206e48a9810112e51f025274',
  embedding_model = 'text-embedding-3-large',
  embedding_dimensions = 1024,
  search_path = 'lightrag,extensions,public',
  notes = 'Phase 5 Packet 2 reviewed PGTableGraphStorage vendor schema from pin 1.5.6.',
  captured_at = timezone('utc', now())
WHERE capture_status = 'deferred'
   OR lightrag_version IN ('deferred', '1.5.6');

-- ---------------------------------------------------------------------------
-- RLS, FORCE RLS, runtime DML policy (app_lightrag only)
-- ---------------------------------------------------------------------------

DO $$
DECLARE
  table_rec record;
  policy_name text;
BEGIN
  FOR table_rec IN
    SELECT tablename
    FROM pg_tables
    WHERE schemaname = 'lightrag'
    ORDER BY tablename
  LOOP
    EXECUTE format(
      'ALTER TABLE lightrag.%I ENABLE ROW LEVEL SECURITY',
      table_rec.tablename
    );
    EXECUTE format(
      'ALTER TABLE lightrag.%I FORCE ROW LEVEL SECURITY',
      table_rec.tablename
    );
    IF table_rec.tablename = 'schema_capture_status' THEN
      CONTINUE;
    END IF;
    policy_name := 'lightrag_' || table_rec.tablename || '_runtime_dml';
    IF NOT EXISTS (
      SELECT 1
      FROM pg_policies
      WHERE schemaname = 'lightrag'
        AND tablename = table_rec.tablename
        AND policyname = policy_name
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON lightrag.%I FOR ALL TO app_lightrag USING (true) WITH CHECK (true)',
        policy_name,
        table_rec.tablename
      );
    END IF;
  END LOOP;
END
$$;

-- ---------------------------------------------------------------------------
-- Grants, default privileges, CREATE revoke, extensions USAGE
-- ---------------------------------------------------------------------------

GRANT USAGE ON SCHEMA lightrag TO app_lightrag;
GRANT USAGE ON SCHEMA extensions TO app_lightrag;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lightrag TO app_lightrag;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lightrag TO app_lightrag;

ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA lightrag
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_lightrag;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA lightrag
  GRANT USAGE, SELECT ON SEQUENCES TO app_lightrag;

REVOKE CREATE ON SCHEMA lightrag FROM PUBLIC;
REVOKE CREATE ON SCHEMA lightrag FROM anon;
REVOKE CREATE ON SCHEMA lightrag FROM authenticated;
REVOKE CREATE ON SCHEMA lightrag FROM app_api;
REVOKE CREATE ON SCHEMA lightrag FROM app_worker;
REVOKE CREATE ON SCHEMA lightrag FROM app_lightrag;
REVOKE CREATE ON SCHEMA lightrag FROM app_checkpointer;
REVOKE CREATE ON SCHEMA lightrag FROM app_audit_writer;

REVOKE ALL ON SCHEMA lightrag FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA lightrag FROM PUBLIC, anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA lightrag FROM PUBLIC, anon, authenticated;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
    REVOKE ALL ON SCHEMA lightrag FROM service_role;
    REVOKE ALL ON ALL TABLES IN SCHEMA lightrag FROM service_role;
    REVOKE ALL ON ALL SEQUENCES IN SCHEMA lightrag FROM service_role;
  END IF;
END
$$;

COMMENT ON TABLE lightrag.lightrag_graph_nodes IS
  'Pin 1.5.6 PGTableGraphStorage nodes. Private vendor storage; not Graph Ready evidence.';
COMMENT ON TABLE lightrag.lightrag_graph_edges IS
  'Pin 1.5.6 PGTableGraphStorage edges. Private vendor storage; not Graph Ready evidence.';
