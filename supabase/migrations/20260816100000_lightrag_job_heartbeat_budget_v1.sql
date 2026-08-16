-- Phase 5 Packet 3: LightRAG job heartbeat/complete/fail, writer lease RPCs,
-- graph budget kinds, default workspace seed. Expand-only. Not Graph Ready.

ALTER TABLE app.company_settings
  ADD COLUMN IF NOT EXISTS daily_graph_index_budget_usd numeric(12, 4)
    NOT NULL DEFAULT 20,
  ADD COLUMN IF NOT EXISTS monthly_graph_maintenance_budget_usd numeric(12, 4)
    NOT NULL DEFAULT 800,
  ADD COLUMN IF NOT EXISTS graph_bulk_window_starts_at timestamptz,
  ADD COLUMN IF NOT EXISTS graph_bulk_window_ends_at timestamptz,
  ADD COLUMN IF NOT EXISTS graph_bulk_approved_at timestamptz;

COMMENT ON COLUMN app.company_settings.daily_graph_index_budget_usd IS
  'Daily USD cap for reservation_kind graph_index. Never mixed with ingestion_daily.';
COMMENT ON COLUMN app.company_settings.monthly_graph_maintenance_budget_usd IS
  'Monthly USD cap for reservation_kind graph_maintenance (delete/ACL/rebuild). QT-COST-003 default 800.';
COMMENT ON COLUMN app.company_settings.graph_bulk_window_starts_at IS
  'Owner-approved bulk onboarding window start. Packet 3 metric stub; null means inactive.';
COMMENT ON COLUMN app.company_settings.graph_bulk_window_ends_at IS
  'Owner-approved bulk onboarding window end. Null means no active window.';
COMMENT ON COLUMN app.company_settings.graph_bulk_approved_at IS
  'When an owner approved the bulk window. Null means no approval.';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'budget_reservations_kind_allowed'
      AND conrelid = 'app.budget_reservations'::regclass
  ) THEN
    ALTER TABLE app.budget_reservations
      ADD CONSTRAINT budget_reservations_kind_allowed
      CHECK (
        reservation_kind IN (
          'ingestion_daily',
          'graph_index',
          'graph_maintenance'
        )
      );
  END IF;
END
$$;

COMMENT ON CONSTRAINT budget_reservations_kind_allowed ON app.budget_reservations IS
  'Normal graph index and maintenance reserves stay distinct from ingestion_daily.';

INSERT INTO app.graph_workspaces (
  workspace_key,
  state,
  embedding_model,
  embedding_dimensions,
  config_snapshot
)
VALUES (
  'company_default',
  'building'::app.graph_workspace_state,
  'text-embedding-3-large',
  1024,
  jsonb_build_object(
    'lightrag_version', '1.5.6',
    'graph_pipeline_version', 'graph_pipeline_v1',
    'chunk_token_size', 1200,
    'chunk_overlap_token_size', 100,
    'tiktoken_model_name', 'gpt-4o-mini',
    'llm_model_max_async', 1
  )
)
ON CONFLICT (workspace_key) DO NOTHING;

CREATE OR REPLACE FUNCTION app.reject_restricted_graph_index_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF COALESCE(NEW.payload_ref->>'reconciliation', '') = 'true' THEN
    RETURN NEW;
  END IF;
  IF NEW.operation IN ('index', 'rebuild') THEN
    PERFORM app.assert_graph_index_allowed(NEW.document_id, NEW.version_id);
  END IF;
  RETURN NEW;
END;
$fn$;

COMMENT ON FUNCTION app.reject_restricted_graph_index_job() IS
  'Reject restricted graph index/rebuild jobs. Reconciliation rebuilds skip the eligibility gate.';

CREATE OR REPLACE FUNCTION app.heartbeat_lightrag_index_job(
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

  UPDATE app.lightrag_index_jobs AS j
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

CREATE OR REPLACE FUNCTION app.complete_lightrag_index_job(
  p_job_id uuid,
  p_owner text,
  p_lease_token text,
  p_result jsonb DEFAULT '{}'::jsonb
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

  UPDATE app.lightrag_index_jobs AS j
  SET
    status = 'completed'::app.job_status,
    payload_ref = COALESCE(j.payload_ref, '{}'::jsonb) || COALESCE(p_result, '{}'::jsonb),
    lease_owner = NULL,
    lease_token = NULL,
    lease_expires_at = NULL,
    heartbeat_at = v_now,
    last_error = NULL,
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

CREATE OR REPLACE FUNCTION app.fail_lightrag_index_job(
  p_job_id uuid,
  p_owner text,
  p_lease_token text,
  p_error_category app.job_error_category,
  p_last_error text,
  p_status app.job_status,
  p_next_attempt_at timestamptz
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

  IF p_status NOT IN (
    'pending'::app.job_status,
    'failed'::app.job_status,
    'dead_letter'::app.job_status
  ) THEN
    RAISE EXCEPTION 'invalid lightrag fail status';
  END IF;

  UPDATE app.lightrag_index_jobs AS j
  SET
    status = p_status,
    error_category = p_error_category,
    last_error = left(COALESCE(p_last_error, ''), 4000),
    next_attempt_at = CASE
      WHEN p_status = 'pending'::app.job_status THEN p_next_attempt_at
      ELSE NULL
    END,
    lease_owner = NULL,
    lease_token = NULL,
    lease_expires_at = NULL,
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

CREATE OR REPLACE FUNCTION app.validate_active_lightrag_lease(
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
  v_ok boolean := false;
BEGIN
  PERFORM app._validate_job_owner(p_owner);

  SELECT EXISTS (
    SELECT 1
    FROM app.lightrag_index_jobs AS j
    WHERE j.id = p_job_id
      AND j.lease_owner = p_owner
      AND j.lease_token = p_lease_token
      AND j.status = 'processing'::app.job_status
      AND j.lease_expires_at IS NOT NULL
      AND j.lease_expires_at >= v_now
  )
  INTO v_ok;

  RETURN v_ok;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.occupy_graph_writer_lease(
  p_owner text,
  p_token text,
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

  IF p_token IS NULL OR length(trim(p_token)) = 0 OR length(p_token) > 256 THEN
    RAISE EXCEPTION 'invalid writer lease token';
  END IF;

  UPDATE app.graph_writer_lease AS lease
  SET
    owner = p_owner,
    token = p_token,
    expires_at = v_now + make_interval(secs => p_lease_seconds),
    updated_at = v_now
  WHERE lease.id = '00000000-0000-0000-0000-000000000001'::uuid
    AND (
      lease.owner IS NULL
      OR lease.expires_at IS NULL
      OR lease.expires_at < v_now
      OR (lease.owner = p_owner AND lease.token = p_token)
    )
  RETURNING lease.id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.heartbeat_graph_writer_lease(
  p_owner text,
  p_token text,
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

  UPDATE app.graph_writer_lease AS lease
  SET
    expires_at = v_now + make_interval(secs => p_lease_seconds),
    updated_at = v_now
  WHERE lease.id = '00000000-0000-0000-0000-000000000001'::uuid
    AND lease.owner = p_owner
    AND lease.token = p_token
    AND lease.expires_at IS NOT NULL
    AND lease.expires_at >= v_now
  RETURNING lease.id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.release_graph_writer_lease(
  p_owner text,
  p_token text
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

  UPDATE app.graph_writer_lease AS lease
  SET
    owner = NULL,
    token = NULL,
    expires_at = NULL,
    updated_at = v_now
  WHERE lease.id = '00000000-0000-0000-0000-000000000001'::uuid
    AND lease.owner = p_owner
    AND lease.token = p_token
  RETURNING lease.id INTO v_updated;

  RETURN v_updated IS NOT NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.validate_active_graph_writer_lease(
  p_owner text,
  p_token text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_ok boolean := false;
BEGIN
  PERFORM app._validate_job_owner(p_owner);

  SELECT EXISTS (
    SELECT 1
    FROM app.graph_writer_lease AS lease
    WHERE lease.id = '00000000-0000-0000-0000-000000000001'::uuid
      AND lease.owner = p_owner
      AND lease.token = p_token
      AND lease.expires_at IS NOT NULL
      AND lease.expires_at >= v_now
  )
  INTO v_ok;

  RETURN v_ok;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.quarantine_graph_workspace(
  p_workspace_key text,
  p_reason text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_id uuid;
BEGIN
  IF p_workspace_key IS NULL OR length(trim(p_workspace_key)) = 0 THEN
    RAISE EXCEPTION 'invalid workspace key';
  END IF;

  UPDATE app.graph_workspaces AS ws
  SET
    state = 'quarantined'::app.graph_workspace_state,
    config_snapshot = COALESCE(ws.config_snapshot, '{}'::jsonb) || jsonb_build_object(
      'reconciliation_required', true,
      'quarantine_reason', left(COALESCE(p_reason, 'unspecified'), 512),
      'quarantined_at', v_now
    ),
    updated_at = v_now
  WHERE ws.workspace_key = p_workspace_key
    AND ws.state IS DISTINCT FROM 'retired'::app.graph_workspace_state
  RETURNING ws.id INTO v_id;

  RETURN v_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.transition_graph_workspace_state(
  p_workspace_key text,
  p_from_states app.graph_workspace_state[],
  p_to_state app.graph_workspace_state,
  p_snapshot jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_id uuid;
BEGIN
  IF p_workspace_key IS NULL OR length(trim(p_workspace_key)) = 0 THEN
    RAISE EXCEPTION 'invalid workspace key';
  END IF;

  UPDATE app.graph_workspaces AS ws
  SET
    state = p_to_state,
    config_snapshot = COALESCE(ws.config_snapshot, '{}'::jsonb)
      || COALESCE(p_snapshot, '{}'::jsonb),
    updated_at = v_now
  WHERE ws.workspace_key = p_workspace_key
    AND ws.state = ANY (p_from_states)
  RETURNING ws.id INTO v_id;

  RETURN v_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.enqueue_graph_reconciliation_job(
  p_workspace_key text,
  p_source_job_id uuid,
  p_reason text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_generation bigint;
  v_idem text;
  v_job_id uuid;
BEGIN
  IF p_workspace_key IS NULL OR length(trim(p_workspace_key)) = 0 THEN
    RAISE EXCEPTION 'invalid workspace key';
  END IF;

  SELECT generation
  INTO v_generation
  FROM app.graph_active_workspace_pointer
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;

  v_idem := format(
    'graph_reconcile:%s:%s',
    p_workspace_key,
    COALESCE(v_generation, 1)
  );

  INSERT INTO app.lightrag_index_jobs (
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    'rebuild'::app.lightrag_job_operation,
    'low'::app.job_priority,
    v_idem,
    jsonb_build_object(
      'reconciliation', true,
      'workspace_key', p_workspace_key,
      'source_job_id', p_source_job_id,
      'reason', left(COALESCE(p_reason, ''), 512),
      'expected_generation', COALESCE(v_generation, 1)
    )
  )
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id INTO v_job_id;

  IF v_job_id IS NULL THEN
    SELECT j.id INTO v_job_id
    FROM app.lightrag_index_jobs AS j
    WHERE j.idempotency_key = v_idem;
  END IF;

  RETURN v_job_id;
END;
$fn$;

REVOKE ALL ON FUNCTION app.heartbeat_lightrag_index_job(uuid, text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.complete_lightrag_index_job(uuid, text, text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.fail_lightrag_index_job(uuid, text, text, app.job_error_category, text, app.job_status, timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.validate_active_lightrag_lease(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.occupy_graph_writer_lease(text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.heartbeat_graph_writer_lease(text, text, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.release_graph_writer_lease(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.validate_active_graph_writer_lease(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.quarantine_graph_workspace(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.transition_graph_workspace_state(text, app.graph_workspace_state[], app.graph_workspace_state, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.enqueue_graph_reconciliation_job(text, uuid, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.heartbeat_lightrag_index_job(uuid, text, text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.complete_lightrag_index_job(uuid, text, text, jsonb) TO app_worker;
GRANT EXECUTE ON FUNCTION app.fail_lightrag_index_job(uuid, text, text, app.job_error_category, text, app.job_status, timestamptz) TO app_worker;
GRANT EXECUTE ON FUNCTION app.validate_active_lightrag_lease(uuid, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.occupy_graph_writer_lease(text, text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.heartbeat_graph_writer_lease(text, text, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.release_graph_writer_lease(text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.validate_active_graph_writer_lease(text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.quarantine_graph_workspace(text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.transition_graph_workspace_state(text, app.graph_workspace_state[], app.graph_workspace_state, jsonb) TO app_worker;
GRANT EXECUTE ON FUNCTION app.enqueue_graph_reconciliation_job(text, uuid, text) TO app_worker;

COMMENT ON FUNCTION app.heartbeat_lightrag_index_job(uuid, text, text, integer) IS
  'Renew a valid LightRAG job lease. app_worker only.';
COMMENT ON FUNCTION app.complete_lightrag_index_job(uuid, text, text, jsonb) IS
  'Complete a leased LightRAG job. Does not mark document versions Graph Ready.';
COMMENT ON FUNCTION app.fail_lightrag_index_job(uuid, text, text, app.job_error_category, text, app.job_status, timestamptz) IS
  'Fail a leased LightRAG job to pending, failed, or dead_letter.';
COMMENT ON FUNCTION app.occupy_graph_writer_lease(text, text, integer) IS
  'Occupy the singleton graph writer lease. Not the vendor schema lock.';
COMMENT ON TABLE app.graph_writer_lease IS
  'Singleton graph-writer lease. Packet 3 occupy/heartbeat/release RPCs. Not Graph Ready.';
