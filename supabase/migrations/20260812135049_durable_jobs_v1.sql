-- Phase 2 Packet 2: durable ingestion, BM25 outbox, LightRAG index, dead-letter queues.

CREATE TABLE app.ingestion_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  job_kind text NOT NULL,
  status app.job_status NOT NULL DEFAULT 'pending',
  priority app.job_priority NOT NULL DEFAULT 'normal',
  idempotency_key text NOT NULL,
  lease_owner text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 8,
  next_attempt_at timestamptz,
  error_category app.job_error_category,
  payload_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT ingestion_jobs_idempotency_key_uq UNIQUE (idempotency_key)
);

CREATE TABLE app.bm25_index_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid REFERENCES app.document_chunks (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  operation app.bm25_job_operation NOT NULL,
  status app.job_status NOT NULL DEFAULT 'pending',
  priority app.job_priority NOT NULL DEFAULT 'normal',
  idempotency_key text NOT NULL,
  lease_owner text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 8,
  next_attempt_at timestamptz,
  error_category app.job_error_category,
  payload_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT bm25_index_jobs_idempotency_key_uq UNIQUE (idempotency_key)
);

CREATE TABLE app.bm25_index_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_number integer NOT NULL,
  normalization_version text NOT NULL DEFAULT search.arabic_normalization_version(),
  index_schema_version text NOT NULL DEFAULT 'bm25_v1',
  is_active boolean NOT NULL DEFAULT false,
  activated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT bm25_index_versions_version_positive CHECK (version_number > 0),
  CONSTRAINT bm25_index_versions_unique_number UNIQUE (version_number)
);

COMMENT ON TABLE app.bm25_index_versions IS
  'Authoritative active BM25 projection/index version pointer in Supabase.';

CREATE TABLE app.lightrag_index_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  operation app.lightrag_job_operation NOT NULL,
  status app.job_status NOT NULL DEFAULT 'pending',
  priority app.job_priority NOT NULL DEFAULT 'normal',
  idempotency_key text NOT NULL,
  lease_owner text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 8,
  next_attempt_at timestamptz,
  error_category app.job_error_category,
  payload_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT lightrag_index_jobs_idempotency_key_uq UNIQUE (idempotency_key)
);

CREATE TABLE app.dead_letter_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_table text NOT NULL,
  source_job_id uuid NOT NULL,
  status app.job_status NOT NULL DEFAULT 'dead_letter',
  priority app.job_priority NOT NULL DEFAULT 'normal',
  idempotency_key text NOT NULL,
  lease_owner text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 1,
  next_attempt_at timestamptz,
  error_category app.job_error_category,
  payload_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT dead_letter_jobs_idempotency_key_uq UNIQUE (idempotency_key)
);

CREATE TRIGGER ingestion_jobs_touch_updated_at
  BEFORE UPDATE ON app.ingestion_jobs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER bm25_index_jobs_touch_updated_at
  BEFORE UPDATE ON app.bm25_index_jobs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER lightrag_index_jobs_touch_updated_at
  BEFORE UPDATE ON app.lightrag_index_jobs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER dead_letter_jobs_touch_updated_at
  BEFORE UPDATE ON app.dead_letter_jobs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
