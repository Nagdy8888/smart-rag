-- Phase 3 Packet 2: lease tokens, job size estimates, operation ledger, claim/lease helpers.

ALTER TABLE app.ingestion_jobs
  ADD COLUMN IF NOT EXISTS lease_token text,
  ADD COLUMN IF NOT EXISTS estimated_size_bytes bigint NOT NULL DEFAULT 0;

ALTER TABLE app.bm25_index_jobs
  ADD COLUMN IF NOT EXISTS lease_token text,
  ADD COLUMN IF NOT EXISTS estimated_size_bytes bigint NOT NULL DEFAULT 0;

ALTER TABLE app.lightrag_index_jobs
  ADD COLUMN IF NOT EXISTS lease_token text,
  ADD COLUMN IF NOT EXISTS estimated_size_bytes bigint NOT NULL DEFAULT 0;

ALTER TABLE app.dead_letter_jobs
  ADD COLUMN IF NOT EXISTS lease_token text;

ALTER TABLE app.ingestion_jobs
  ADD CONSTRAINT ingestion_jobs_estimated_size_nonneg
  CHECK (estimated_size_bytes >= 0);

ALTER TABLE app.bm25_index_jobs
  ADD CONSTRAINT bm25_index_jobs_estimated_size_nonneg
  CHECK (estimated_size_bytes >= 0);

ALTER TABLE app.lightrag_index_jobs
  ADD CONSTRAINT lightrag_index_jobs_estimated_size_nonneg
  CHECK (estimated_size_bytes >= 0);

CREATE TABLE app.job_operation_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_table text NOT NULL,
  job_id uuid NOT NULL,
  operation_key text NOT NULL,
  lease_token text NOT NULL,
  status text NOT NULL,
  result_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT job_operation_ledger_unique UNIQUE (job_table, job_id, operation_key),
  CONSTRAINT job_operation_ledger_status_check CHECK (
    status IN ('started', 'completed', 'failed')
  )
);

CREATE TRIGGER job_operation_ledger_touch_updated_at
  BEFORE UPDATE ON app.job_operation_ledger
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE INDEX ingestion_jobs_claim_idx
  ON app.ingestion_jobs (status, priority, created_at, estimated_size_bytes)
  WHERE status IN ('pending', 'processing');

CREATE INDEX bm25_index_jobs_claim_idx
  ON app.bm25_index_jobs (status, priority, created_at, estimated_size_bytes)
  WHERE status IN ('pending', 'processing');

CREATE INDEX lightrag_index_jobs_claim_idx
  ON app.lightrag_index_jobs (status, priority, created_at, estimated_size_bytes)
  WHERE status IN ('pending', 'processing');

CREATE INDEX dead_letter_jobs_poll_idx
  ON app.dead_letter_jobs (status, created_at);

COMMENT ON TABLE app.job_operation_ledger IS
  'Idempotent side-effect ledger for ingestion graph nodes and worker transitions.';

-- ---------------------------------------------------------------------------
-- Shared lease validation helpers
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app._validate_job_lease_seconds(p_lease_seconds integer)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF p_lease_seconds IS NULL OR p_lease_seconds < 30 OR p_lease_seconds > 3600 THEN
    RAISE EXCEPTION 'invalid lease seconds (expected 30..3600)';
  END IF;
END;
$fn$;

CREATE OR REPLACE FUNCTION app._validate_job_owner(p_owner text)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF p_owner IS NULL OR length(trim(p_owner)) = 0 OR length(p_owner) > 256 THEN
    RAISE EXCEPTION 'invalid lease owner';
  END IF;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.heartbeat_ingestion_job(
  p_job_id uuid,
  p_owner text,
  p_lease_token text,
  p_lease_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_updated uuid;
BEGIN
  PERFORM app._validate_job_owner(p_owner);
  PERFORM app._validate_job_lease_seconds(p_lease_seconds);

  UPDATE app.ingestion_jobs AS j
  SET
    heartbeat_at = v_now,
    lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
    updated_at = v_now
  WHERE j.id = p_job_id
    AND j.lease_owner = p_owner
    AND j.lease_token = p_lease_token
    AND j.status = 'processing'::app.job_status
    AND j.lease_expires_at IS NOT NULL
    AND j.lease_expires_at >= v_now
  RETURNING j.id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.complete_ingestion_job(
  p_job_id uuid,
  p_owner text,
  p_lease_token text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_updated uuid;
BEGIN
  PERFORM app._validate_job_owner(p_owner);

  UPDATE app.ingestion_jobs AS j
  SET
    status = 'completed'::app.job_status,
    lease_owner = NULL,
    lease_token = NULL,
    lease_expires_at = NULL,
    heartbeat_at = v_now,
    updated_at = v_now
  WHERE j.id = p_job_id
    AND j.lease_owner = p_owner
    AND j.lease_token = p_lease_token
    AND j.status = 'processing'::app.job_status
    AND j.lease_expires_at IS NOT NULL
    AND j.lease_expires_at >= v_now
  RETURNING j.id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.cancel_ingestion_job(
  p_job_id uuid,
  p_owner text,
  p_lease_token text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_updated uuid;
BEGIN
  PERFORM app._validate_job_owner(p_owner);

  UPDATE app.ingestion_jobs AS j
  SET
    status = 'cancelled'::app.job_status,
    lease_owner = NULL,
    lease_token = NULL,
    lease_expires_at = NULL,
    updated_at = v_now
  WHERE j.id = p_job_id
    AND (
      (
        j.status = 'processing'::app.job_status
        AND j.lease_owner = p_owner
        AND j.lease_token = p_lease_token
        AND j.lease_expires_at IS NOT NULL
        AND j.lease_expires_at >= v_now
      )
      OR j.status = 'pending'::app.job_status
    )
  RETURNING j.id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.record_job_operation_ledger(
  p_job_table text,
  p_job_id uuid,
  p_operation_key text,
  p_lease_token text,
  p_status text,
  p_result_ref jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_ledger_id uuid;
  v_valid boolean := false;
BEGIN
  IF p_job_table NOT IN (
    'ingestion_jobs',
    'bm25_index_jobs',
    'lightrag_index_jobs',
    'dead_letter_jobs'
  ) THEN
    RAISE EXCEPTION 'unsupported job_table';
  END IF;

  IF p_operation_key IS NULL OR length(trim(p_operation_key)) = 0 THEN
    RAISE EXCEPTION 'invalid operation_key';
  END IF;

  IF p_status NOT IN ('started', 'completed', 'failed') THEN
    RAISE EXCEPTION 'invalid ledger status';
  END IF;

  IF p_job_table = 'ingestion_jobs' THEN
    SELECT EXISTS (
      SELECT 1
      FROM app.ingestion_jobs AS j
      WHERE j.id = p_job_id
        AND j.lease_token = p_lease_token
        AND j.status = 'processing'::app.job_status
        AND j.lease_expires_at IS NOT NULL
        AND j.lease_expires_at >= v_now
    )
    INTO v_valid;
  ELSIF p_job_table = 'bm25_index_jobs' THEN
    SELECT EXISTS (
      SELECT 1
      FROM app.bm25_index_jobs AS j
      WHERE j.id = p_job_id
        AND j.lease_token = p_lease_token
        AND j.status = 'processing'::app.job_status
        AND j.lease_expires_at IS NOT NULL
        AND j.lease_expires_at >= v_now
    )
    INTO v_valid;
  ELSIF p_job_table = 'lightrag_index_jobs' THEN
    SELECT EXISTS (
      SELECT 1
      FROM app.lightrag_index_jobs AS j
      WHERE j.id = p_job_id
        AND j.lease_token = p_lease_token
        AND j.status = 'processing'::app.job_status
        AND j.lease_expires_at IS NOT NULL
        AND j.lease_expires_at >= v_now
    )
    INTO v_valid;
  ELSE
    SELECT EXISTS (
      SELECT 1
      FROM app.dead_letter_jobs AS j
      WHERE j.id = p_job_id
        AND j.lease_token = p_lease_token
        AND j.status = 'dead_letter'::app.job_status
    )
    INTO v_valid;
  END IF;

  IF NOT v_valid THEN
    RAISE EXCEPTION 'invalid or expired lease for ledger write';
  END IF;

  INSERT INTO app.job_operation_ledger (
    job_table,
    job_id,
    operation_key,
    lease_token,
    status,
    result_ref
  )
  VALUES (
    p_job_table,
    p_job_id,
    p_operation_key,
    p_lease_token,
    p_status,
    COALESCE(p_result_ref, '{}'::jsonb)
  )
  ON CONFLICT (job_table, job_id, operation_key) DO NOTHING
  RETURNING id INTO v_ledger_id;

  IF v_ledger_id IS NULL THEN
    SELECT l.id
    INTO v_ledger_id
    FROM app.job_operation_ledger AS l
    WHERE l.job_table = p_job_table
      AND l.job_id = p_job_id
      AND l.operation_key = p_operation_key;
  END IF;

  RETURN v_ledger_id;
END;
$fn$;

-- ---------------------------------------------------------------------------
-- Claim functions (FOR UPDATE SKIP LOCKED)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.claim_ingestion_job(
  p_owner text,
  p_lease_seconds integer
)
RETURNS SETOF app.ingestion_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_job_id uuid;
  v_token text;
BEGIN
  PERFORM app._validate_job_owner(p_owner);
  PERFORM app._validate_job_lease_seconds(p_lease_seconds);

  SELECT j.id
  INTO v_job_id
  FROM app.ingestion_jobs AS j
  WHERE (
      j.status = 'pending'::app.job_status
      AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= v_now)
    )
    OR (
      j.status = 'processing'::app.job_status
      AND j.lease_expires_at IS NOT NULL
      AND j.lease_expires_at < v_now
    )
  ORDER BY
    CASE j.priority
      WHEN 'critical'::app.job_priority THEN 1
      WHEN 'high'::app.job_priority THEN 2
      WHEN 'normal'::app.job_priority THEN 3
      WHEN 'low'::app.job_priority THEN 4
    END,
    j.created_at ASC,
    j.estimated_size_bytes ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_job_id IS NULL THEN
    RETURN;
  END IF;

  v_token := gen_random_uuid()::text;

  RETURN QUERY
  UPDATE app.ingestion_jobs AS j
  SET
    status = 'processing'::app.job_status,
    lease_owner = p_owner,
    lease_token = v_token,
    lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
    heartbeat_at = v_now,
    attempt_count = j.attempt_count + 1,
    updated_at = v_now
  WHERE j.id = v_job_id
  RETURNING j.*;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.claim_bm25_index_job(
  p_owner text,
  p_lease_seconds integer
)
RETURNS SETOF app.bm25_index_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_job_id uuid;
  v_token text;
BEGIN
  PERFORM app._validate_job_owner(p_owner);
  PERFORM app._validate_job_lease_seconds(p_lease_seconds);

  SELECT j.id
  INTO v_job_id
  FROM app.bm25_index_jobs AS j
  WHERE (
      j.status = 'pending'::app.job_status
      AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= v_now)
    )
    OR (
      j.status = 'processing'::app.job_status
      AND j.lease_expires_at IS NOT NULL
      AND j.lease_expires_at < v_now
    )
  ORDER BY
    CASE j.priority
      WHEN 'critical'::app.job_priority THEN 1
      WHEN 'high'::app.job_priority THEN 2
      WHEN 'normal'::app.job_priority THEN 3
      WHEN 'low'::app.job_priority THEN 4
    END,
    j.created_at ASC,
    j.estimated_size_bytes ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_job_id IS NULL THEN
    RETURN;
  END IF;

  v_token := gen_random_uuid()::text;

  RETURN QUERY
  UPDATE app.bm25_index_jobs AS j
  SET
    status = 'processing'::app.job_status,
    lease_owner = p_owner,
    lease_token = v_token,
    lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
    heartbeat_at = v_now,
    attempt_count = j.attempt_count + 1,
    updated_at = v_now
  WHERE j.id = v_job_id
  RETURNING j.*;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.claim_lightrag_index_job(
  p_owner text,
  p_lease_seconds integer
)
RETURNS SETOF app.lightrag_index_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_job_id uuid;
  v_token text;
  v_pending_index bigint;
BEGIN
  PERFORM app._validate_job_owner(p_owner);
  PERFORM app._validate_job_lease_seconds(p_lease_seconds);

  SELECT count(*)
  INTO v_pending_index
  FROM app.lightrag_index_jobs AS j
  WHERE j.status = 'pending'::app.job_status
    AND j.operation = 'index'::app.lightrag_job_operation;

  SELECT j.id
  INTO v_job_id
  FROM app.lightrag_index_jobs AS j
  WHERE (
      (
        j.status = 'pending'::app.job_status
        AND (j.next_attempt_at IS NULL OR j.next_attempt_at <= v_now)
        AND (
          j.operation <> 'index'::app.lightrag_job_operation
          OR v_pending_index <= 50
        )
      )
      OR (
        j.status = 'processing'::app.job_status
        AND j.lease_expires_at IS NOT NULL
        AND j.lease_expires_at < v_now
      )
    )
  ORDER BY
    CASE j.priority
      WHEN 'critical'::app.job_priority THEN 1
      WHEN 'high'::app.job_priority THEN 2
      WHEN 'normal'::app.job_priority THEN 3
      WHEN 'low'::app.job_priority THEN 4
    END,
    j.created_at ASC,
    j.estimated_size_bytes ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_job_id IS NULL THEN
    RETURN;
  END IF;

  v_token := gen_random_uuid()::text;

  RETURN QUERY
  UPDATE app.lightrag_index_jobs AS j
  SET
    status = 'processing'::app.job_status,
    lease_owner = p_owner,
    lease_token = v_token,
    lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
    heartbeat_at = v_now,
    attempt_count = j.attempt_count + 1,
    updated_at = v_now
  WHERE j.id = v_job_id
  RETURNING j.*;
END;
$fn$;

-- ---------------------------------------------------------------------------
-- RLS and grants
-- ---------------------------------------------------------------------------

ALTER TABLE app.job_operation_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY job_operation_ledger_worker_rw
  ON app.job_operation_ledger
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY dead_letter_jobs_worker_rw
  ON app.dead_letter_jobs
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE ON app.job_operation_ledger TO app_worker;
GRANT SELECT ON app.company_settings TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.budget_reservations TO app_worker;

CREATE POLICY company_settings_worker_read
  ON app.company_settings
  FOR SELECT
  TO app_worker
  USING (true);

CREATE POLICY budget_reservations_worker_rw
  ON app.budget_reservations
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

REVOKE ALL ON FUNCTION app.claim_ingestion_job(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.claim_bm25_index_job(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.claim_lightrag_index_job(text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.heartbeat_ingestion_job(uuid, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.complete_ingestion_job(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.cancel_ingestion_job(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.record_job_operation_ledger(text, uuid, text, text, text, jsonb) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.claim_ingestion_job(text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.claim_bm25_index_job(text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.claim_lightrag_index_job(text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.heartbeat_ingestion_job(uuid, text, text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.complete_ingestion_job(uuid, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.cancel_ingestion_job(uuid, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.record_job_operation_ledger(text, uuid, text, text, text, jsonb) TO app_worker;

COMMENT ON FUNCTION app.claim_lightrag_index_job(text, integer) IS
  'Claims LightRAG jobs with graph-handoff pause: pending index operations >50 block new index claims.';
