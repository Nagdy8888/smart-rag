-- Phase 3 gap close-out Run 1: role-scoped ingestion retry RPC.
-- Dead-letter replay inserts a new job and retains the original DL row.
-- Failed-but-not-DL (backoff pending or explicit failed) only clears
-- next_attempt_at and, for failed, returns the row to pending. last_error
-- and attempt_count are never wiped.

CREATE OR REPLACE FUNCTION app.retry_ingestion_job(p_job_id uuid)
RETURNS TABLE (
  id uuid,
  document_id uuid,
  version_id uuid,
  job_kind text,
  status app.job_status,
  priority app.job_priority,
  idempotency_key text,
  lease_owner text,
  lease_token text,
  lease_expires_at timestamptz,
  heartbeat_at timestamptz,
  attempt_count integer,
  max_attempts integer,
  next_attempt_at timestamptz,
  error_category app.job_error_category,
  payload_ref jsonb,
  estimated_size_bytes bigint,
  last_error text,
  created_at timestamptz,
  updated_at timestamptz,
  detail text,
  original_job_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_job app.ingestion_jobs%ROWTYPE;
  v_dl app.dead_letter_jobs%ROWTYPE;
  v_new app.ingestion_jobs%ROWTYPE;
  v_suffix text;
  v_payload jsonb;
BEGIN
  SELECT * INTO v_job
  FROM app.ingestion_jobs AS j
  WHERE j.id = p_job_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'ingestion_job_not_found'
      USING ERRCODE = 'P0002';
  END IF;

  IF v_job.status = 'dead_letter'::app.job_status THEN
    SELECT * INTO v_dl
    FROM app.dead_letter_jobs AS d
    WHERE d.source_table = 'ingestion_jobs'
      AND d.source_job_id = p_job_id
    ORDER BY d.created_at DESC
    LIMIT 1;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'dead_letter_row_not_found'
        USING ERRCODE = 'P0002';
    END IF;

    v_suffix := to_char(clock_timestamp(), 'YYYYMMDDHH24MISSUS')
      || ':'
      || substr(gen_random_uuid()::text, 1, 8);
    v_payload := COALESCE(v_job.payload_ref, '{}'::jsonb)
      || jsonb_build_object(
        'replay_of_dead_letter_id', v_dl.id,
        'replay_of_source_job_id', v_job.id,
        'original_last_error', v_dl.last_error
      );

    INSERT INTO app.ingestion_jobs (
      document_id,
      version_id,
      job_kind,
      priority,
      idempotency_key,
      payload_ref,
      estimated_size_bytes,
      max_attempts,
      status
    )
    VALUES (
      v_job.document_id,
      v_job.version_id,
      v_job.job_kind,
      v_job.priority,
      'replay:' || v_job.idempotency_key || ':' || v_suffix,
      v_payload,
      COALESCE(v_job.estimated_size_bytes, 0),
      v_job.max_attempts,
      'pending'::app.job_status
    )
    RETURNING * INTO v_new;

    UPDATE app.dead_letter_jobs AS dl
    SET
      payload_ref = COALESCE(dl.payload_ref, '{}'::jsonb) || jsonb_build_object(
        'last_replay_job_id', v_new.id,
        'last_replay_at', timezone('utc', now())
      ),
      updated_at = timezone('utc', now())
    WHERE dl.id = v_dl.id;

    RETURN QUERY SELECT
      v_new.id,
      v_new.document_id,
      v_new.version_id,
      v_new.job_kind,
      v_new.status,
      v_new.priority,
      v_new.idempotency_key,
      v_new.lease_owner,
      v_new.lease_token,
      v_new.lease_expires_at,
      v_new.heartbeat_at,
      v_new.attempt_count,
      v_new.max_attempts,
      v_new.next_attempt_at,
      v_new.error_category,
      v_new.payload_ref,
      v_new.estimated_size_bytes,
      v_new.last_error,
      v_new.created_at,
      v_new.updated_at,
      'dead_letter_replayed'::text,
      v_job.id;
    RETURN;
  END IF;

  IF v_job.status = 'pending'::app.job_status
     AND v_job.next_attempt_at IS NOT NULL THEN
    UPDATE app.ingestion_jobs AS j
    SET
      next_attempt_at = NULL,
      updated_at = timezone('utc', now())
    WHERE j.id = p_job_id
    RETURNING * INTO v_job;

    RETURN QUERY SELECT
      v_job.id,
      v_job.document_id,
      v_job.version_id,
      v_job.job_kind,
      v_job.status,
      v_job.priority,
      v_job.idempotency_key,
      v_job.lease_owner,
      v_job.lease_token,
      v_job.lease_expires_at,
      v_job.heartbeat_at,
      v_job.attempt_count,
      v_job.max_attempts,
      v_job.next_attempt_at,
      v_job.error_category,
      v_job.payload_ref,
      v_job.estimated_size_bytes,
      v_job.last_error,
      v_job.created_at,
      v_job.updated_at,
      'backoff_cleared'::text,
      v_job.id;
    RETURN;
  END IF;

  IF v_job.status = 'failed'::app.job_status THEN
    UPDATE app.ingestion_jobs AS j
    SET
      status = 'pending'::app.job_status,
      next_attempt_at = NULL,
      updated_at = timezone('utc', now())
    WHERE j.id = p_job_id
    RETURNING * INTO v_job;

    RETURN QUERY SELECT
      v_job.id,
      v_job.document_id,
      v_job.version_id,
      v_job.job_kind,
      v_job.status,
      v_job.priority,
      v_job.idempotency_key,
      v_job.lease_owner,
      v_job.lease_token,
      v_job.lease_expires_at,
      v_job.heartbeat_at,
      v_job.attempt_count,
      v_job.max_attempts,
      v_job.next_attempt_at,
      v_job.error_category,
      v_job.payload_ref,
      v_job.estimated_size_bytes,
      v_job.last_error,
      v_job.created_at,
      v_job.updated_at,
      'failed_requeued'::text,
      v_job.id;
    RETURN;
  END IF;

  RAISE EXCEPTION 'retry_not_allowed'
    USING ERRCODE = 'P0001';
END;
$fn$;

COMMENT ON FUNCTION app.retry_ingestion_job(uuid) IS
  'Owner/admin retry: DL replay creates a new job; backoff/failed only clears next_attempt_at.';

REVOKE ALL ON FUNCTION app.retry_ingestion_job(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.retry_ingestion_job(uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.retry_ingestion_job(uuid) TO app_worker;
