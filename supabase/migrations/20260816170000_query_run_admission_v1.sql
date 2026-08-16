-- Phase 6 Packet 1: authenticated query-run admission, query_run reservations,
-- run-local optimistic consume, immutable usage, heartbeat/expiry true-up,
-- and run-scoped restricted-evidence audit. Expand-only except CHECK widening.

-- ---------------------------------------------------------------------------
-- Constraint widening: add query_run to reservation_kind CHECK.
-- DROP CONSTRAINT of a CHECK is allowed by CI as additive allowed values,
-- not data-destructive DROP COLUMN / DROP TABLE.
-- ---------------------------------------------------------------------------

ALTER TABLE app.budget_reservations
  DROP CONSTRAINT budget_reservations_kind_allowed;

ALTER TABLE app.budget_reservations
  ADD CONSTRAINT budget_reservations_kind_allowed
  CHECK (
    reservation_kind IN (
      'ingestion_daily',
      'graph_index',
      'graph_maintenance',
      'query_run'
    )
  );

COMMENT ON CONSTRAINT budget_reservations_kind_allowed ON app.budget_reservations IS
  'query_run is distinct from ingestion_daily and graph_maintenance (QT-COST-003).';

-- ---------------------------------------------------------------------------
-- Run admission columns
-- ---------------------------------------------------------------------------

ALTER TABLE app.runs
  ADD COLUMN IF NOT EXISTS route_family text,
  ADD COLUMN IF NOT EXISTS reservation_id uuid REFERENCES app.budget_reservations (id),
  ADD COLUMN IF NOT EXISTS deadline_at timestamptz,
  ADD COLUMN IF NOT EXISTS recursion_limit integer,
  ADD COLUMN IF NOT EXISTS correction_ceiling integer,
  ADD COLUMN IF NOT EXISTS subquestion_ceiling integer,
  ADD COLUMN IF NOT EXISTS model_call_ceiling integer,
  ADD COLUMN IF NOT EXISTS tool_ceiling integer,
  ADD COLUMN IF NOT EXISTS discovery_ceiling integer,
  ADD COLUMN IF NOT EXISTS manifest_ceiling integer,
  ADD COLUMN IF NOT EXISTS side_effect_ceiling integer,
  ADD COLUMN IF NOT EXISTS request_payload_hash text,
  ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;

COMMENT ON COLUMN app.runs.route_family IS
  'Server-assigned Phase 6 family. Clients cannot set role, budget, or ceilings.';
COMMENT ON COLUMN app.runs.reservation_id IS
  'Run-local query_run reservation consumed by gateway calls.';
COMMENT ON COLUMN app.runs.request_payload_hash IS
  'SHA-256 of canonical admit payload; same key with a different hash is a collision.';
COMMENT ON COLUMN app.runs.heartbeat_at IS
  'Last durable heartbeat. Packet 7 owns checkpoint/event reaping, not this column.';

ALTER TABLE app.runs
  DROP CONSTRAINT IF EXISTS runs_route_family_allowed;
ALTER TABLE app.runs
  ADD CONSTRAINT runs_route_family_allowed
  CHECK (
    route_family IS NULL
    OR route_family IN (
      'hybrid',
      'combined',
      'structured_table',
      'composite',
      'graph_inspection',
      'no_retrieval',
      'scoped_refusal'
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS runs_creator_conversation_idempotency_uq
  ON app.runs (creator_user_id, conversation_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS runs_active_deadline_idx
  ON app.runs (status, deadline_at)
  WHERE status IN ('pending', 'running');

-- ---------------------------------------------------------------------------
-- Run-local reservation remaining holds and optimistic version
-- ---------------------------------------------------------------------------

ALTER TABLE app.budget_reservations
  ADD COLUMN IF NOT EXISTS optimistic_version integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS remaining_usd numeric(12, 6),
  ADD COLUMN IF NOT EXISTS remaining_prompt_tokens integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS remaining_completion_tokens integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS committed_amount_usd numeric(12, 6);

COMMENT ON COLUMN app.budget_reservations.optimistic_version IS
  'Run-local consume version. Gateway calls never SELECT FOR UPDATE company_settings.';
COMMENT ON COLUMN app.budget_reservations.remaining_usd IS
  'Remaining hold for query_run. Ingestion kinds leave this null.';
COMMENT ON COLUMN app.budget_reservations.committed_amount_usd IS
  'Settled actual spend. True-up never exceeds the original envelope.';

ALTER TABLE app.budget_reservations
  DROP CONSTRAINT IF EXISTS budget_reservations_optimistic_version_positive;
ALTER TABLE app.budget_reservations
  ADD CONSTRAINT budget_reservations_optimistic_version_positive
  CHECK (optimistic_version >= 1);

-- ---------------------------------------------------------------------------
-- Immutable usage ledger columns
-- ---------------------------------------------------------------------------

ALTER TABLE app.llm_usage
  ADD COLUMN IF NOT EXISTS reservation_id uuid REFERENCES app.budget_reservations (id),
  ADD COLUMN IF NOT EXISTS reservation_version integer,
  ADD COLUMN IF NOT EXISTS provider_attempt_id text,
  ADD COLUMN IF NOT EXISTS timeout_after_send boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN app.llm_usage.reservation_id IS
  'Run-local reservation charged for this provider attempt.';
COMMENT ON COLUMN app.llm_usage.provider_attempt_id IS
  'Idempotent provider attempt id, including timeout-after-send.';
COMMENT ON COLUMN app.llm_usage.timeout_after_send IS
  'True when the HTTP request was sent and the response was lost.';

ALTER TABLE app.llm_usage
  DROP CONSTRAINT IF EXISTS llm_usage_kind_allowed;
ALTER TABLE app.llm_usage
  ADD CONSTRAINT llm_usage_kind_allowed
  CHECK (
    usage_kind IN (
      'profile',
      'rewrite',
      'lightrag',
      'rerank',
      'answer',
      'summary',
      'verifier',
      'embedding'
    )
  );

CREATE UNIQUE INDEX IF NOT EXISTS llm_usage_provider_attempt_uq
  ON app.llm_usage (provider_attempt_id)
  WHERE provider_attempt_id IS NOT NULL;

CREATE OR REPLACE FUNCTION app.block_llm_usage_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $fn$
BEGIN
  RAISE EXCEPTION 'llm_usage is append-only';
END;
$fn$;

DROP TRIGGER IF EXISTS llm_usage_block_mutation ON app.llm_usage;
CREATE TRIGGER llm_usage_block_mutation
  BEFORE UPDATE OR DELETE ON app.llm_usage
  FOR EACH ROW
  EXECUTE FUNCTION app.block_llm_usage_mutation();

ALTER TABLE app.llm_usage FORCE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Restricted-read correlation to citation (content-minimized)
-- ---------------------------------------------------------------------------

ALTER TABLE app.restricted_read_events
  ADD COLUMN IF NOT EXISTS citation_id uuid REFERENCES app.citations (id) ON DELETE SET NULL;

COMMENT ON COLUMN app.restricted_read_events.citation_id IS
  'Citation identifier only. Passage text is never stored.';

-- ---------------------------------------------------------------------------
-- Server-owned envelope table (must match Python ceilings.py)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.query_route_envelope(p_route_family text)
RETURNS TABLE (
  deadline_seconds integer,
  recursion_limit integer,
  correction_ceiling integer,
  subquestion_ceiling integer,
  model_call_ceiling integer,
  tool_ceiling integer,
  discovery_ceiling integer,
  manifest_ceiling integer,
  side_effect_ceiling integer,
  envelope_usd numeric,
  envelope_prompt_tokens integer,
  envelope_completion_tokens integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  CASE p_route_family
    WHEN 'hybrid' THEN
      deadline_seconds := 25;
      model_call_ceiling := 7;
      tool_ceiling := 4;
      envelope_usd := 2.80;
      envelope_prompt_tokens := 56000;
      envelope_completion_tokens := 14000;
    WHEN 'combined' THEN
      deadline_seconds := 45;
      model_call_ceiling := 8;
      tool_ceiling := 4;
      envelope_usd := 3.20;
      envelope_prompt_tokens := 64000;
      envelope_completion_tokens := 16000;
    WHEN 'structured_table' THEN
      deadline_seconds := 30;
      model_call_ceiling := 6;
      tool_ceiling := 4;
      envelope_usd := 2.40;
      envelope_prompt_tokens := 48000;
      envelope_completion_tokens := 12000;
    WHEN 'composite' THEN
      deadline_seconds := 50;
      model_call_ceiling := 9;
      tool_ceiling := 5;
      envelope_usd := 3.60;
      envelope_prompt_tokens := 72000;
      envelope_completion_tokens := 18000;
    WHEN 'graph_inspection' THEN
      deadline_seconds := 10;
      model_call_ceiling := 3;
      tool_ceiling := 4;
      envelope_usd := 0.75;
      envelope_prompt_tokens := 12000;
      envelope_completion_tokens := 4500;
    WHEN 'no_retrieval' THEN
      -- QUALITY_TARGETS has no sixth deadline; Hybrid 25s envelope.
      deadline_seconds := 25;
      model_call_ceiling := 7;
      tool_ceiling := 4;
      envelope_usd := 2.80;
      envelope_prompt_tokens := 56000;
      envelope_completion_tokens := 14000;
    WHEN 'scoped_refusal' THEN
      deadline_seconds := 25;
      model_call_ceiling := 7;
      tool_ceiling := 4;
      envelope_usd := 2.80;
      envelope_prompt_tokens := 56000;
      envelope_completion_tokens := 14000;
    ELSE
      RAISE EXCEPTION 'query_admission:unknown_route_family';
  END CASE;

  recursion_limit := 24;
  correction_ceiling := 1;
  subquestion_ceiling := 3;
  discovery_ceiling := 1;
  manifest_ceiling := 3;
  side_effect_ceiling := 1;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.query_route_envelope(text) IS
  'Server-owned Phase 6 route envelopes. Not executable by clients as authority.';

REVOKE ALL ON FUNCTION app.query_route_envelope(text) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Internal settlement (no shared-row locks)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.true_up_query_reservation_internal(p_reservation_id uuid)
RETURNS TABLE (
  reservation_id uuid,
  status app.budget_reservation_status,
  committed_amount_usd numeric,
  already_settled boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  reservation app.budget_reservations%ROWTYPE;
  usage_sum numeric(12, 6);
  actual numeric(12, 6);
  new_status app.budget_reservation_status;
BEGIN
  SELECT * INTO reservation
  FROM app.budget_reservations AS br
  WHERE br.id = p_reservation_id;

  IF NOT FOUND OR reservation.reservation_kind IS DISTINCT FROM 'query_run' THEN
    RAISE EXCEPTION 'query_admission:reservation_not_found';
  END IF;

  IF reservation.status IN (
      'committed'::app.budget_reservation_status,
      'released'::app.budget_reservation_status,
      'expired'::app.budget_reservation_status
    )
    AND reservation.committed_amount_usd IS NOT NULL THEN
    reservation_id := reservation.id;
    status := reservation.status;
    committed_amount_usd := reservation.committed_amount_usd;
    already_settled := true;
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT COALESCE(sum(u.cost_usd), 0)
  INTO usage_sum
  FROM app.llm_usage AS u
  WHERE u.reservation_id = p_reservation_id;

  actual := LEAST(usage_sum, reservation.amount_usd);
  IF actual <= 0 THEN
    new_status := 'released'::app.budget_reservation_status;
    actual := 0;
  ELSE
    new_status := 'committed'::app.budget_reservation_status;
  END IF;

  UPDATE app.budget_reservations AS br
  SET
    status = new_status,
    committed_amount_usd = actual,
    remaining_usd = 0,
    remaining_prompt_tokens = 0,
    remaining_completion_tokens = 0,
    committed_at = CASE
      WHEN new_status = 'committed'::app.budget_reservation_status
        THEN timezone('utc', now())
      ELSE br.committed_at
    END,
    released_at = CASE
      WHEN new_status = 'released'::app.budget_reservation_status
        THEN timezone('utc', now())
      ELSE br.released_at
    END,
    updated_at = timezone('utc', now())
  WHERE br.id = p_reservation_id
    AND br.status = 'reserved'::app.budget_reservation_status;

  IF NOT FOUND THEN
    SELECT * INTO reservation
    FROM app.budget_reservations AS br
    WHERE br.id = p_reservation_id;
    reservation_id := reservation.id;
    status := reservation.status;
    committed_amount_usd := COALESCE(reservation.committed_amount_usd, 0);
    already_settled := true;
    RETURN NEXT;
    RETURN;
  END IF;

  reservation_id := p_reservation_id;
  status := new_status;
  committed_amount_usd := actual;
  already_settled := false;
  RETURN NEXT;
END;
$fn$;

REVOKE ALL ON FUNCTION app.true_up_query_reservation_internal(uuid) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Admit
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.admit_query_run(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_idempotency_key text,
  p_payload_hash text,
  p_route_family text,
  p_session_id text DEFAULT NULL,
  p_token_issued_at timestamptz DEFAULT NULL
)
RETURNS TABLE (
  run_id uuid,
  reservation_id uuid,
  reconnect boolean,
  status app.run_status,
  route_family text,
  deadline_at timestamptz,
  recursion_limit integer,
  correction_ceiling integer,
  subquestion_ceiling integer,
  model_call_ceiling integer,
  tool_ceiling integer,
  discovery_ceiling integer,
  manifest_ceiling integer,
  side_effect_ceiling integer,
  reserved_amount_usd numeric,
  remaining_usd numeric,
  remaining_prompt_tokens integer,
  remaining_completion_tokens integer,
  optimistic_version integer,
  heartbeat_at timestamptz,
  request_payload_hash text
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
  profile_row app.profiles%ROWTYPE;
  company_row app.company_settings%ROWTYPE;
  existing_run app.runs%ROWTYPE;
  existing_res app.budget_reservations%ROWTYPE;
  envelope RECORD;
  monthly_cap numeric(12, 4);
  monthly_used numeric(12, 6);
  active_runs integer;
  new_run_id uuid;
  new_res_id uuid;
  now_utc timestamptz;
  new_deadline timestamptz;
  new_expires timestamptz;
BEGIN
  IF p_idempotency_key IS NULL
    OR p_idempotency_key !~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' THEN
    RAISE EXCEPTION 'query_admission:invalid_idempotency_key';
  END IF;

  IF p_payload_hash IS NULL OR p_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'query_admission:invalid_payload_hash';
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  SELECT * INTO profile_row
  FROM app.profiles AS p
  WHERE p.user_id = caller_user_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF p_session_id IS NOT NULL
    AND EXISTS (
      SELECT 1
      FROM app.revoked_sessions AS rs
      WHERE rs.session_id = p_session_id
    ) THEN
    RAISE EXCEPTION 'query_admission:session_revoked';
  END IF;

  IF profile_row.session_revoked_at IS NOT NULL
    AND (
      p_token_issued_at IS NULL
      OR p_token_issued_at <= profile_row.session_revoked_at
    ) THEN
    RAISE EXCEPTION 'query_admission:session_revoked';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:conversation_not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_admission:conversation_deleted';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:conversation_forbidden';
  END IF;

  SELECT * INTO existing_run
  FROM app.runs AS r
  WHERE r.creator_user_id = caller_user_id
    AND r.conversation_id = p_conversation_id
    AND r.idempotency_key = p_idempotency_key;

  IF FOUND THEN
    IF existing_run.request_payload_hash IS DISTINCT FROM p_payload_hash THEN
      RAISE EXCEPTION 'query_admission:key_collision';
    END IF;
    SELECT * INTO existing_res
    FROM app.budget_reservations AS br
    WHERE br.id = existing_run.reservation_id;
    run_id := existing_run.id;
    reservation_id := existing_run.reservation_id;
    reconnect := true;
    status := existing_run.status;
    route_family := existing_run.route_family;
    deadline_at := existing_run.deadline_at;
    recursion_limit := existing_run.recursion_limit;
    correction_ceiling := existing_run.correction_ceiling;
    subquestion_ceiling := existing_run.subquestion_ceiling;
    model_call_ceiling := existing_run.model_call_ceiling;
    tool_ceiling := existing_run.tool_ceiling;
    discovery_ceiling := existing_run.discovery_ceiling;
    manifest_ceiling := existing_run.manifest_ceiling;
    side_effect_ceiling := existing_run.side_effect_ceiling;
    reserved_amount_usd := existing_res.amount_usd;
    remaining_usd := COALESCE(existing_res.remaining_usd, 0);
    remaining_prompt_tokens := existing_res.remaining_prompt_tokens;
    remaining_completion_tokens := existing_res.remaining_completion_tokens;
    optimistic_version := existing_res.optimistic_version;
    heartbeat_at := existing_run.heartbeat_at;
    request_payload_hash := existing_run.request_payload_hash;
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT * INTO envelope
  FROM app.query_route_envelope(p_route_family);

  now_utc := timezone('utc', now());
  new_deadline := now_utc + make_interval(secs => envelope.deadline_seconds);
  new_expires := new_deadline + interval '5 minutes';

  BEGIN
    SELECT * INTO company_row
    FROM app.company_settings AS cs
    WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
    FOR UPDATE;

    SELECT * INTO profile_row
    FROM app.profiles AS p
    WHERE p.user_id = caller_user_id
    FOR UPDATE;

    SELECT count(*)::integer
    INTO active_runs
    FROM app.runs AS r
    WHERE r.status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      )
      AND r.deadline_at IS NOT NULL
      AND r.deadline_at > now_utc;

    IF active_runs >= 5 THEN
      RAISE EXCEPTION 'query_admission:concurrency_cap';
    END IF;

    monthly_cap := COALESCE(
      profile_row.monthly_llm_budget_usd,
      company_row.monthly_llm_budget_usd,
      200
    );

    SELECT COALESCE(
      sum(
        CASE
          WHEN br.status = 'committed'::app.budget_reservation_status
            THEN COALESCE(br.committed_amount_usd, br.amount_usd)
          ELSE br.amount_usd
        END
      ),
      0
    )
    INTO monthly_used
    FROM app.budget_reservations AS br
    WHERE br.reservation_kind = 'query_run'
      AND br.status IN (
        'reserved'::app.budget_reservation_status,
        'committed'::app.budget_reservation_status
      )
      AND br.created_at >= date_trunc('month', now_utc)
      AND (
        br.status = 'committed'::app.budget_reservation_status
        OR br.expires_at > now_utc
      );

    IF monthly_used + envelope.envelope_usd > monthly_cap THEN
      RAISE EXCEPTION 'query_admission:budget_exhausted';
    END IF;

    new_res_id := gen_random_uuid();
    new_run_id := gen_random_uuid();

    INSERT INTO app.budget_reservations (
      id,
      user_id,
      reservation_kind,
      amount_usd,
      remaining_usd,
      remaining_prompt_tokens,
      remaining_completion_tokens,
      optimistic_version,
      status,
      expires_at
    )
    VALUES (
      new_res_id,
      caller_user_id,
      'query_run',
      envelope.envelope_usd,
      envelope.envelope_usd,
      envelope.envelope_prompt_tokens,
      envelope.envelope_completion_tokens,
      1,
      'reserved'::app.budget_reservation_status,
      new_expires
    );

    INSERT INTO app.runs (
      id,
      conversation_id,
      creator_user_id,
      status,
      graph_name,
      idempotency_key,
      route_family,
      reservation_id,
      deadline_at,
      recursion_limit,
      correction_ceiling,
      subquestion_ceiling,
      model_call_ceiling,
      tool_ceiling,
      discovery_ceiling,
      manifest_ceiling,
      side_effect_ceiling,
      request_payload_hash,
      heartbeat_at,
      started_at
    )
    VALUES (
      new_run_id,
      p_conversation_id,
      caller_user_id,
      'pending'::app.run_status,
      'query',
      p_idempotency_key,
      p_route_family,
      new_res_id,
      new_deadline,
      envelope.recursion_limit,
      envelope.correction_ceiling,
      envelope.subquestion_ceiling,
      envelope.model_call_ceiling,
      envelope.tool_ceiling,
      envelope.discovery_ceiling,
      envelope.manifest_ceiling,
      envelope.side_effect_ceiling,
      p_payload_hash,
      now_utc,
      now_utc
    );

    UPDATE app.budget_reservations
    SET run_id = new_run_id
    WHERE id = new_res_id;
  EXCEPTION
    WHEN unique_violation THEN
      SELECT * INTO existing_run
      FROM app.runs AS r
      WHERE r.creator_user_id = caller_user_id
        AND r.conversation_id = p_conversation_id
        AND r.idempotency_key = p_idempotency_key;
      IF NOT FOUND THEN
        RAISE EXCEPTION 'query_admission:key_collision';
      END IF;
      IF existing_run.request_payload_hash IS DISTINCT FROM p_payload_hash THEN
        RAISE EXCEPTION 'query_admission:key_collision';
      END IF;
      SELECT * INTO existing_res
      FROM app.budget_reservations AS br
      WHERE br.id = existing_run.reservation_id;
      run_id := existing_run.id;
      reservation_id := existing_run.reservation_id;
      reconnect := true;
      status := existing_run.status;
      route_family := existing_run.route_family;
      deadline_at := existing_run.deadline_at;
      recursion_limit := existing_run.recursion_limit;
      correction_ceiling := existing_run.correction_ceiling;
      subquestion_ceiling := existing_run.subquestion_ceiling;
      model_call_ceiling := existing_run.model_call_ceiling;
      tool_ceiling := existing_run.tool_ceiling;
      discovery_ceiling := existing_run.discovery_ceiling;
      manifest_ceiling := existing_run.manifest_ceiling;
      side_effect_ceiling := existing_run.side_effect_ceiling;
      reserved_amount_usd := existing_res.amount_usd;
      remaining_usd := COALESCE(existing_res.remaining_usd, 0);
      remaining_prompt_tokens := existing_res.remaining_prompt_tokens;
      remaining_completion_tokens := existing_res.remaining_completion_tokens;
      optimistic_version := existing_res.optimistic_version;
      heartbeat_at := existing_run.heartbeat_at;
      request_payload_hash := existing_run.request_payload_hash;
      RETURN NEXT;
      RETURN;
  END;

  run_id := new_run_id;
  reservation_id := new_res_id;
  reconnect := false;
  status := 'pending'::app.run_status;
  route_family := p_route_family;
  deadline_at := new_deadline;
  recursion_limit := envelope.recursion_limit;
  correction_ceiling := envelope.correction_ceiling;
  subquestion_ceiling := envelope.subquestion_ceiling;
  model_call_ceiling := envelope.model_call_ceiling;
  tool_ceiling := envelope.tool_ceiling;
  discovery_ceiling := envelope.discovery_ceiling;
  manifest_ceiling := envelope.manifest_ceiling;
  side_effect_ceiling := envelope.side_effect_ceiling;
  reserved_amount_usd := envelope.envelope_usd;
  remaining_usd := envelope.envelope_usd;
  remaining_prompt_tokens := envelope.envelope_prompt_tokens;
  remaining_completion_tokens := envelope.envelope_completion_tokens;
  optimistic_version := 1;
  heartbeat_at := now_utc;
  request_payload_hash := p_payload_hash;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.admit_query_run(
  uuid, text, bigint, uuid, text, text, text, text, timestamptz
) IS
  'Atomically admits one query run or reconnects. Server-derived auth only.';

REVOKE ALL ON FUNCTION app.admit_query_run(
  uuid, text, bigint, uuid, text, text, text, text, timestamptz
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.admit_query_run(
  uuid, text, bigint, uuid, text, text, text, text, timestamptz
) TO app_api;

-- ---------------------------------------------------------------------------
-- Consume (run-local optimistic version; no shared budget-row locks)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.consume_query_reservation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_reservation_id uuid,
  p_expected_version integer,
  p_amount_usd numeric,
  p_prompt_tokens integer,
  p_completion_tokens integer
)
RETURNS TABLE (
  reservation_id uuid,
  optimistic_version integer,
  remaining_usd numeric,
  remaining_prompt_tokens integer,
  remaining_completion_tokens integer
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_owner uuid;
  current_version integer;
  current_remaining numeric(12, 6);
  current_status app.budget_reservation_status;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF p_amount_usd IS NULL OR p_amount_usd <= 0
    OR p_prompt_tokens IS NULL OR p_prompt_tokens < 0
    OR p_completion_tokens IS NULL OR p_completion_tokens < 0 THEN
    RAISE EXCEPTION 'query_admission:invalid_consume_amount';
  END IF;

  SELECT r.creator_user_id
  INTO run_owner
  FROM app.runs AS r
  WHERE r.reservation_id = p_reservation_id;

  IF NOT FOUND OR run_owner IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:run_forbidden';
  END IF;

  UPDATE app.budget_reservations AS br
  SET
    remaining_usd = br.remaining_usd - p_amount_usd,
    remaining_prompt_tokens = br.remaining_prompt_tokens - p_prompt_tokens,
    remaining_completion_tokens = br.remaining_completion_tokens - p_completion_tokens,
    optimistic_version = br.optimistic_version + 1,
    updated_at = timezone('utc', now())
  WHERE br.id = p_reservation_id
    AND br.reservation_kind = 'query_run'
    AND br.optimistic_version = p_expected_version
    AND br.status = 'reserved'::app.budget_reservation_status
    AND br.remaining_usd >= p_amount_usd
    AND br.remaining_prompt_tokens >= p_prompt_tokens
    AND br.remaining_completion_tokens >= p_completion_tokens
  RETURNING
    br.id,
    br.optimistic_version,
    br.remaining_usd,
    br.remaining_prompt_tokens,
    br.remaining_completion_tokens
  INTO
    reservation_id,
    optimistic_version,
    remaining_usd,
    remaining_prompt_tokens,
    remaining_completion_tokens;

  IF FOUND THEN
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT br.optimistic_version, br.remaining_usd, br.status
  INTO current_version, current_remaining, current_status
  FROM app.budget_reservations AS br
  WHERE br.id = p_reservation_id
    AND br.reservation_kind = 'query_run';

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:reservation_not_found';
  END IF;
  IF current_status IS DISTINCT FROM 'reserved'::app.budget_reservation_status THEN
    RAISE EXCEPTION 'query_admission:reservation_not_active';
  END IF;
  IF current_version IS DISTINCT FROM p_expected_version THEN
    RAISE EXCEPTION 'query_admission:optimistic_version_conflict';
  END IF;
  RAISE EXCEPTION 'query_admission:reservation_exhausted';
END;
$fn$;

COMMENT ON FUNCTION app.consume_query_reservation(
  uuid, text, bigint, uuid, integer, numeric, integer, integer
) IS
  'Optimistic consume of one query_run reservation. Does not lock company_settings.';

REVOKE ALL ON FUNCTION app.consume_query_reservation(
  uuid, text, bigint, uuid, integer, numeric, integer, integer
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.consume_query_reservation(
  uuid, text, bigint, uuid, integer, numeric, integer, integer
) TO app_api;

-- ---------------------------------------------------------------------------
-- Immutable usage insert
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.record_query_llm_usage(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_reservation_id uuid,
  p_reservation_version integer,
  p_usage_kind text,
  p_model_id text,
  p_provider_attempt_id text,
  p_prompt_tokens integer,
  p_completion_tokens integer,
  p_cost_usd numeric,
  p_timeout_after_send boolean
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_owner uuid;
  new_id uuid;
  total_tokens integer;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF p_usage_kind NOT IN (
    'profile', 'rewrite', 'lightrag', 'rerank', 'answer',
    'summary', 'verifier', 'embedding'
  ) THEN
    RAISE EXCEPTION 'query_admission:unknown_usage_kind';
  END IF;

  IF p_model_id IS NULL OR btrim(p_model_id) = '' OR char_length(p_model_id) > 128 THEN
    RAISE EXCEPTION 'query_admission:invalid_model_id';
  END IF;

  IF p_provider_attempt_id IS NULL
    OR btrim(p_provider_attempt_id) = ''
    OR char_length(p_provider_attempt_id) > 128 THEN
    RAISE EXCEPTION 'query_admission:invalid_provider_attempt_id';
  END IF;

  SELECT r.creator_user_id
  INTO run_owner
  FROM app.runs AS r
  WHERE r.id = p_run_id
    AND r.reservation_id = p_reservation_id;

  IF NOT FOUND OR run_owner IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:run_forbidden';
  END IF;

  total_tokens := COALESCE(p_prompt_tokens, 0) + COALESCE(p_completion_tokens, 0);

  INSERT INTO app.llm_usage (
    user_id,
    run_id,
    reservation_id,
    reservation_version,
    model_id,
    prompt_tokens,
    completion_tokens,
    total_tokens,
    cost_usd,
    usage_kind,
    provider_attempt_id,
    timeout_after_send
  )
  VALUES (
    caller_user_id,
    p_run_id,
    p_reservation_id,
    p_reservation_version,
    p_model_id,
    COALESCE(p_prompt_tokens, 0),
    COALESCE(p_completion_tokens, 0),
    total_tokens,
    COALESCE(p_cost_usd, 0),
    p_usage_kind,
    p_provider_attempt_id,
    COALESCE(p_timeout_after_send, false)
  )
  ON CONFLICT (provider_attempt_id)
    WHERE provider_attempt_id IS NOT NULL
  DO NOTHING
  RETURNING id INTO new_id;

  IF new_id IS NULL THEN
    SELECT u.id
    INTO new_id
    FROM app.llm_usage AS u
    WHERE u.provider_attempt_id = p_provider_attempt_id;
  END IF;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.record_query_llm_usage(
  uuid, text, bigint, uuid, uuid, integer, text, text, text, integer, integer, numeric, boolean
) IS
  'Append-only usage insert for one provider attempt, including timeout-after-send.';

REVOKE ALL ON FUNCTION app.record_query_llm_usage(
  uuid, text, bigint, uuid, uuid, integer, text, text, text, integer, integer, numeric, boolean
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.record_query_llm_usage(
  uuid, text, bigint, uuid, uuid, integer, text, text, text, integer, integer, numeric, boolean
) TO app_api;

-- ---------------------------------------------------------------------------
-- Caller true-up
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.true_up_query_reservation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_reservation_id uuid
)
RETURNS TABLE (
  reservation_id uuid,
  status app.budget_reservation_status,
  committed_amount_usd numeric,
  already_settled boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_owner uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  SELECT r.creator_user_id
  INTO run_owner
  FROM app.runs AS r
  WHERE r.reservation_id = p_reservation_id;

  IF NOT FOUND OR run_owner IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:run_forbidden';
  END IF;

  RETURN QUERY
  SELECT *
  FROM app.true_up_query_reservation_internal(p_reservation_id);
END;
$fn$;

COMMENT ON FUNCTION app.true_up_query_reservation(uuid, text, bigint, uuid) IS
  'Idempotent settlement of one query_run reservation from immutable usage.';

REVOKE ALL ON FUNCTION app.true_up_query_reservation(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.true_up_query_reservation(uuid, text, bigint, uuid)
  TO app_api;

-- ---------------------------------------------------------------------------
-- Heartbeat
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.heartbeat_query_run(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS timestamptz
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  now_utc timestamptz;
  new_heartbeat timestamptz;
  max_expires timestamptz;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  now_utc := timezone('utc', now());

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:run_forbidden';
  END IF;

  IF run_row.deadline_at IS NOT NULL AND now_utc >= run_row.deadline_at THEN
    RAISE EXCEPTION 'query_admission:deadline_exhausted';
  END IF;

  UPDATE app.runs
  SET
    heartbeat_at = now_utc,
    status = CASE
      WHEN status = 'pending'::app.run_status THEN 'running'::app.run_status
      ELSE status
    END
  WHERE id = p_run_id
    AND status IN (
      'pending'::app.run_status,
      'running'::app.run_status
    )
  RETURNING heartbeat_at INTO new_heartbeat;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:run_not_active';
  END IF;

  max_expires := COALESCE(run_row.deadline_at, now_utc) + interval '10 minutes';
  UPDATE app.budget_reservations
  SET
    expires_at = LEAST(max_expires, now_utc + interval '5 minutes'),
    updated_at = now_utc
  WHERE id = run_row.reservation_id
    AND reservation_kind = 'query_run'
    AND status = 'reserved'::app.budget_reservation_status;

  RETURN new_heartbeat;
END;
$fn$;

COMMENT ON FUNCTION app.heartbeat_query_run(uuid, text, bigint, uuid) IS
  'Durable query-run heartbeat. Extends reservation TTL without shared-row consume locks.';

REVOKE ALL ON FUNCTION app.heartbeat_query_run(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.heartbeat_query_run(uuid, text, bigint, uuid)
  TO app_api;

-- ---------------------------------------------------------------------------
-- Expiry / crash reconciler (not packet 7 event reaper)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.reconcile_expired_query_runs()
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  settled integer := 0;
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT r.id, r.reservation_id
    FROM app.runs AS r
    LEFT JOIN app.budget_reservations AS br ON br.id = r.reservation_id
    WHERE r.graph_name = 'query'
      AND r.status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      )
      AND (
        (r.deadline_at IS NOT NULL AND r.deadline_at < timezone('utc', now()))
        OR (
          r.heartbeat_at IS NOT NULL
          AND r.heartbeat_at < timezone('utc', now()) - interval '2 minutes'
        )
        OR (
          br.id IS NOT NULL
          AND br.status = 'reserved'::app.budget_reservation_status
          AND br.expires_at < timezone('utc', now())
        )
      )
  LOOP
    IF rec.reservation_id IS NOT NULL THEN
      PERFORM app.true_up_query_reservation_internal(rec.reservation_id);
    END IF;
    UPDATE app.runs
    SET status = 'partial'::app.run_status,
        completed_at = timezone('utc', now())
    WHERE id = rec.id
      AND status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      );
    settled := settled + 1;
  END LOOP;
  RETURN settled;
END;
$fn$;

COMMENT ON FUNCTION app.reconcile_expired_query_runs() IS
  'Idempotent query reservation true-up for deadline/heartbeat/expiry crashes.';

REVOKE ALL ON FUNCTION app.reconcile_expired_query_runs()
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.reconcile_expired_query_runs() TO app_worker;
GRANT EXECUTE ON FUNCTION app.reconcile_expired_query_runs() TO app_api;

-- ---------------------------------------------------------------------------
-- Restricted evidence included in a completed run
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.record_run_restricted_evidence(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_document_id uuid,
  p_version_id uuid,
  p_session_id text,
  p_citation_id uuid DEFAULT NULL,
  p_purpose text DEFAULT 'evidence',
  p_signed_url_expires_at timestamptz DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  document_row app.documents%ROWTYPE;
  audit_id uuid;
  restricted_read_id uuid;
  citation_run uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF p_purpose NOT IN ('evidence', 'preview', 'download') THEN
    RAISE EXCEPTION 'restricted read purpose rejected';
  END IF;

  IF p_session_id IS NULL
    OR btrim(p_session_id) = ''
    OR char_length(p_session_id) > 256 THEN
    RAISE EXCEPTION 'bounded session identifier required';
  END IF;

  IF p_purpose = 'download' THEN
    IF p_signed_url_expires_at IS NULL
      OR p_signed_url_expires_at <= timezone('utc', now()) THEN
      RAISE EXCEPTION 'download expiry must be in the future';
    END IF;
  ELSIF p_signed_url_expires_at IS NOT NULL THEN
    RAISE EXCEPTION 'signed URL expiry is valid only for download';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:run_forbidden';
  END IF;

  IF p_citation_id IS NOT NULL THEN
    SELECT c.run_id
    INTO citation_run
    FROM app.citations AS c
    WHERE c.id = p_citation_id;
    IF NOT FOUND OR citation_run IS DISTINCT FROM p_run_id THEN
      RAISE EXCEPTION 'query_admission:citation_forbidden';
    END IF;
  END IF;

  SELECT document.*
  INTO document_row
  FROM app.documents AS document
  WHERE document.id = p_document_id
  FOR SHARE;

  IF NOT FOUND
    OR document_row.deleted_at IS NOT NULL
    OR document_row.visibility IS DISTINCT FROM 'restricted'::app.document_visibility
    OR document_row.current_version_id IS DISTINCT FROM p_version_id THEN
    RAISE EXCEPTION 'active restricted current version not found';
  END IF;

  IF NOT app.caller_can_read_document(
    caller_user_id,
    caller_role,
    p_document_id
  ) THEN
    RAISE EXCEPTION 'restricted read denied';
  END IF;

  audit_id := app.append_audit_event(
    'restricted_read.authorized',
    caller_user_id,
    caller_role::app.user_role,
    'document',
    p_document_id,
    app.current_authorization_version(),
    jsonb_build_object(
      'access_surface', p_purpose,
      'version_id', p_version_id,
      'run_id', p_run_id,
      'citation_id', p_citation_id
    ),
    p_purpose,
    'document_version',
    p_version_id,
    p_session_id
  );

  INSERT INTO app.restricted_read_events (
    audit_event_id,
    actor_user_id,
    document_id,
    version_id,
    run_id,
    citation_id,
    purpose,
    signed_url_expires_at
  )
  VALUES (
    audit_id,
    caller_user_id,
    p_document_id,
    p_version_id,
    p_run_id,
    p_citation_id,
    p_purpose,
    p_signed_url_expires_at
  )
  RETURNING id INTO restricted_read_id;

  RETURN restricted_read_id;
END;
$fn$;

COMMENT ON FUNCTION app.record_run_restricted_evidence(
  uuid, text, bigint, uuid, uuid, uuid, text, uuid, text, timestamptz
) IS
  'Append-only restricted evidence for a run: actor, version, run, citation, purpose. No passage text.';

REVOKE ALL ON FUNCTION app.record_run_restricted_evidence(
  uuid, text, bigint, uuid, uuid, uuid, text, uuid, text, timestamptz
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.record_run_restricted_evidence(
  uuid, text, bigint, uuid, uuid, uuid, text, uuid, text, timestamptz
) TO app_api;
