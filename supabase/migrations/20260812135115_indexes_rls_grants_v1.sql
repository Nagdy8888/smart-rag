-- Phase 2 Packet 2: supporting indexes, RLS enablement (deny-by-default), default privileges.

CREATE INDEX documents_visibility_generation_idx
  ON app.documents (visibility_generation);

CREATE INDEX documents_current_version_id_idx
  ON app.documents (current_version_id)
  WHERE deleted_at IS NULL;

CREATE INDEX document_versions_document_id_idx
  ON app.document_versions (document_id);

CREATE INDEX document_versions_status_idx
  ON app.document_versions (status);

CREATE INDEX document_chunks_version_id_idx
  ON app.document_chunks (version_id)
  WHERE deleted_at IS NULL;

CREATE INDEX document_chunks_document_id_idx
  ON app.document_chunks (document_id);

CREATE INDEX document_search_terms_chunk_id_idx
  ON app.document_search_terms (chunk_id);

CREATE INDEX document_search_terms_normalized_idx
  ON app.document_search_terms (term_normalized);

CREATE INDEX ingestion_jobs_status_next_attempt_idx
  ON app.ingestion_jobs (status, next_attempt_at, priority);

CREATE INDEX bm25_index_jobs_status_next_attempt_idx
  ON app.bm25_index_jobs (status, next_attempt_at, priority);

CREATE INDEX lightrag_index_jobs_status_next_attempt_idx
  ON app.lightrag_index_jobs (status, next_attempt_at, priority);

CREATE INDEX conversations_creator_user_id_idx
  ON app.conversations (creator_user_id)
  WHERE deleted_at IS NULL;

CREATE INDEX runs_conversation_id_idx
  ON app.runs (conversation_id);

CREATE INDEX runs_creator_user_id_idx
  ON app.runs (creator_user_id);

CREATE INDEX citations_run_id_idx
  ON app.citations (run_id);

CREATE INDEX llm_usage_recorded_at_idx
  ON app.llm_usage (recorded_at);

CREATE INDEX audit_events_created_at_idx
  ON app.audit_events (created_at);

CREATE INDEX audit_events_event_type_idx
  ON app.audit_events (event_type);

-- HNSW index on embeddings deferred to Phase 3 bulk ingest gate; column type pinned here.
COMMENT ON COLUMN app.document_chunks.embedding IS
  'Hybrid embedding vector(1024) per ADR-embedding-model-dimension. HNSW index added after RAM gate.';

ALTER TABLE app.profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.company_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.allowed_email_domains ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.team_invitations ENABLE ROW LEVEL SECURITY;
ALTER TABLE private.auth_rate_limit_buckets ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_acl ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.source_approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_scan_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_tables ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_table_columns ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.document_search_terms ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.search_aliases ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.ingestion_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.bm25_index_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.bm25_index_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.lightrag_index_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.dead_letter_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.lightrag_source_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.lightrag_chunk_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_evidence_map ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_entity_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.user_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tool_catalog ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tool_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tool_permissions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.tool_usage_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.llm_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.budget_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.upload_quota_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.audit_chain_anchors ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.restricted_read_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.admin_notifications ENABLE ROW LEVEL SECURITY;

ALTER TABLE langgraph.checkpoint_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoint_blobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoint_writes ENABLE ROW LEVEL SECURITY;
ALTER TABLE lightrag.schema_capture_status ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON SCHEMA private FROM PUBLIC;
REVOKE ALL ON SCHEMA langgraph FROM PUBLIC;
REVOKE ALL ON SCHEMA lightrag FROM PUBLIC;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA private FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA langgraph FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA lightrag FROM PUBLIC;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA private FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA langgraph FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA lightrag FROM PUBLIC;

GRANT USAGE ON SCHEMA app TO postgres;
GRANT USAGE ON SCHEMA private TO postgres;
GRANT USAGE ON SCHEMA langgraph TO postgres;
GRANT USAGE ON SCHEMA lightrag TO postgres;

GRANT ALL ON ALL TABLES IN SCHEMA app TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA private TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA langgraph TO postgres;
GRANT ALL ON ALL TABLES IN SCHEMA lightrag TO postgres;

GRANT ALL ON ALL SEQUENCES IN SCHEMA app TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA private TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA langgraph TO postgres;
GRANT ALL ON ALL SEQUENCES IN SCHEMA lightrag TO postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA lightrag REVOKE ALL ON TABLES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA private GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT ALL ON TABLES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA lightrag GRANT ALL ON TABLES TO postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph REVOKE ALL ON SEQUENCES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA lightrag REVOKE ALL ON SEQUENCES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA private GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph GRANT ALL ON SEQUENCES TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA lightrag GRANT ALL ON SEQUENCES TO postgres;
