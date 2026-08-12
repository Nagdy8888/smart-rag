-- Phase 2 Packet 2: application schemas, shared enums, and durable-job column contract.

CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA IF NOT EXISTS private;

COMMENT ON SCHEMA app IS
  'Canonical Smart RAG business tables. RLS enabled; policies arrive in Packet 3.';
COMMENT ON SCHEMA private IS
  'Server-only internals (degraded rate limits, future audit helpers). Not browser exposed.';

CREATE TYPE app.user_role AS ENUM ('owner', 'admin', 'member', 'viewer');
CREATE TYPE app.document_visibility AS ENUM ('company_visible', 'restricted');
CREATE TYPE app.document_status AS ENUM (
  'uploaded',
  'scanning',
  'parsing',
  'hybrid_ready',
  'graph_pending',
  'graph_ready',
  'graph_ineligible',
  'deletion_pending',
  'failed'
);
CREATE TYPE app.source_type AS ENUM ('file_upload', 'website_crawl');
CREATE TYPE app.scan_result AS ENUM (
  'clean',
  'infected',
  'unscannable',
  'stale_signature',
  'over_limit'
);
CREATE TYPE app.approval_status AS ENUM ('pending', 'approved', 'rejected', 'revoked');
CREATE TYPE app.job_status AS ENUM (
  'pending',
  'processing',
  'completed',
  'failed',
  'dead_letter',
  'cancelled'
);
CREATE TYPE app.job_priority AS ENUM ('low', 'normal', 'high', 'critical');
CREATE TYPE app.job_error_category AS ENUM (
  'transient',
  'permanent',
  'budget',
  'authorization',
  'validation',
  'unknown'
);
CREATE TYPE app.bm25_job_operation AS ENUM ('upsert', 'delete');
CREATE TYPE app.lightrag_job_operation AS ENUM ('index', 'remove', 'graph_acl_remove', 'rebuild');
CREATE TYPE app.run_status AS ENUM (
  'pending',
  'running',
  'completed',
  'failed',
  'cancelled',
  'partial'
);
CREATE TYPE app.budget_reservation_status AS ENUM (
  'reserved',
  'committed',
  'released',
  'expired'
);
CREATE TYPE app.tool_permission_level AS ENUM ('none', 'read', 'execute', 'admin');

COMMENT ON TYPE app.job_status IS
  'Shared durable-job lifecycle. Lease/idempotency columns are required on every queue table.';

CREATE OR REPLACE FUNCTION app.touch_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  NEW.updated_at := timezone('utc', now());
  RETURN NEW;
END;
$fn$;

COMMENT ON FUNCTION app.touch_updated_at() IS
  'Maintains UTC updated_at on mutable app tables.';

-- Documented durable-job column contract applied identically on queue tables:
-- status, priority, idempotency_key UNIQUE, lease_owner, lease_expires_at,
-- heartbeat_at, attempt_count, max_attempts, next_attempt_at, error_category,
-- payload_ref (jsonb pointer to Storage/canonical rows; never authoritative secrets).
