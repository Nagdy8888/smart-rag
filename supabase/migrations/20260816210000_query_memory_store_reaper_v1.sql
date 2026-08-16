-- Phase 6 Packet 7: LangGraph store schema (pinned library SQL, schema langgraph),
-- idempotency-key hash retention, 7/30-day reaper, conversation deletion RPC,
-- LangSmith deletion requests, feedback tags, and citation unavailable flag.
-- Expand-only. Runtime never calls PostgresStore.setup() or PostgresSaver.setup().
-- Copied store DDL from langgraph.store.postgres.base.MIGRATIONS (4 statements,
-- indices 0-3). CREATE INDEX CONCURRENTLY is omitted because Supabase migrations
-- run inside a transaction; columns match the pinned library exactly.

-- ---------------------------------------------------------------------------
-- LangGraph store (PostgresStore.MIGRATIONS 0-3) in schema langgraph
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS langgraph.store_migrations (
  v integer PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS langgraph.store (
  prefix text NOT NULL,
  key text NOT NULL,
  value jsonb NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (prefix, key)
);

CREATE INDEX IF NOT EXISTS store_prefix_idx
  ON langgraph.store USING btree (prefix text_pattern_ops);

ALTER TABLE langgraph.store
  ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP WITH TIME ZONE,
  ADD COLUMN IF NOT EXISTS ttl_minutes INT;

CREATE INDEX IF NOT EXISTS idx_store_expires_at
  ON langgraph.store (expires_at)
  WHERE expires_at IS NOT NULL;

INSERT INTO langgraph.store_migrations (v)
VALUES (0), (1), (2), (3)
ON CONFLICT (v) DO NOTHING;

COMMENT ON TABLE langgraph.store IS
  'Pinned LangGraph PostgresStore rows. Compact summaries/preferences only. Runtime does not auto-migrate.';
COMMENT ON TABLE langgraph.store_migrations IS
  'Pinned LangGraph PostgresStore schema versions (0-3). Runtime does not call PostgresStore.setup().';

ALTER TABLE langgraph.store ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.store FORCE ROW LEVEL SECURITY;
ALTER TABLE langgraph.store_migrations ENABLE ROW LEVEL SECURITY;
ALTER TABLE langgraph.store_migrations FORCE ROW LEVEL SECURITY;

CREATE POLICY langgraph_store_checkpointer_all
  ON langgraph.store
  FOR ALL
  TO app_checkpointer
  USING (true)
  WITH CHECK (true);

CREATE POLICY langgraph_store_migrations_checkpointer_all
  ON langgraph.store_migrations
  FOR ALL
  TO app_checkpointer
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE, DELETE ON langgraph.store TO app_checkpointer;
GRANT SELECT, INSERT, UPDATE, DELETE ON langgraph.store_migrations TO app_checkpointer;
GRANT ALL ON langgraph.store TO postgres;
GRANT ALL ON langgraph.store_migrations TO postgres;
ALTER DEFAULT PRIVILEGES IN SCHEMA langgraph
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_checkpointer;

REVOKE ALL ON langgraph.store FROM PUBLIC, anon, authenticated;
REVOKE ALL ON langgraph.store_migrations FROM PUBLIC, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Idempotency key hash (survives 7-day key NULL; one-paid-run)
-- ---------------------------------------------------------------------------

ALTER TABLE app.runs
  ADD COLUMN IF NOT EXISTS idempotency_key_hash text;

COMMENT ON COLUMN app.runs.idempotency_key_hash IS
  'SHA-256 of the client idempotency key. Reaper NULLs the plaintext key after 7 days; this hash preserves one-paid-run uniqueness.';

UPDATE app.runs
SET idempotency_key_hash = encode(
  sha256(convert_to(idempotency_key, 'UTF8')),
  'hex'
)
WHERE idempotency_key IS NOT NULL
  AND idempotency_key_hash IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS runs_creator_conversation_idempotency_hash_uq
  ON app.runs (creator_user_id, conversation_id, idempotency_key_hash)
  WHERE idempotency_key_hash IS NOT NULL;

CREATE OR REPLACE FUNCTION app.runs_preserve_idempotency_hash()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NEW.idempotency_key IS NOT NULL
    AND (
      NEW.idempotency_key_hash IS NULL
      OR TG_OP = 'INSERT'
      OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
    ) THEN
    NEW.idempotency_key_hash := encode(
      sha256(convert_to(NEW.idempotency_key, 'UTF8')),
      'hex'
    );
  END IF;
  IF TG_OP = 'UPDATE'
    AND NEW.idempotency_key IS NULL
    AND OLD.idempotency_key_hash IS NOT NULL THEN
    NEW.idempotency_key_hash := OLD.idempotency_key_hash;
  END IF;
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS runs_preserve_idempotency_hash ON app.runs;
CREATE TRIGGER runs_preserve_idempotency_hash
  BEFORE INSERT OR UPDATE ON app.runs
  FOR EACH ROW
  EXECUTE FUNCTION app.runs_preserve_idempotency_hash();

-- ---------------------------------------------------------------------------
-- Feedback tags and citation unavailable flag
-- ---------------------------------------------------------------------------

ALTER TABLE app.user_feedback
  ADD COLUMN IF NOT EXISTS tag text;

COMMENT ON COLUMN app.user_feedback.tag IS
  'Required Phase 6 feedback tag. Exact allow-listed string; never merged.';

ALTER TABLE app.user_feedback
  DROP CONSTRAINT IF EXISTS user_feedback_tag_allowed;
ALTER TABLE app.user_feedback
  ADD CONSTRAINT user_feedback_tag_allowed
  CHECK (
    tag IS NULL
    OR tag IN (
      'chunk/cleaning loss',
      'profile field wrong',
      'candidate miss',
      'wrong rerank',
      'bad refusal/overconfident answer',
      'missed relationship',
      'wrong route',
      'wrong calculation',
      'bad citation',
      'insufficient graph'
    )
  );

ALTER TABLE app.citations
  ADD COLUMN IF NOT EXISTS source_unavailable boolean NOT NULL DEFAULT false;

COMMENT ON COLUMN app.citations.source_unavailable IS
  'True when the cited source was deleted. Historical messages are not rewritten.';

-- ---------------------------------------------------------------------------
-- LangSmith durable deletion requests (request + retry, not cloud proof)
-- ---------------------------------------------------------------------------

CREATE TABLE app.langsmith_deletion_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id_hash text NOT NULL,
  run_id_hashes text[] NOT NULL DEFAULT '{}'::text[],
  hashed_trace_keys text[] NOT NULL DEFAULT '{}'::text[],
  status text NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 24,
  requested_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  retry_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  sla_deadline_at timestamptz NOT NULL,
  last_error text,
  request_recorded_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT langsmith_deletion_status_allowed CHECK (
    status IN ('pending', 'retrying', 'request_recorded', 'sla_expired')
  ),
  CONSTRAINT langsmith_deletion_attempts_nonnegative CHECK (attempts >= 0)
);

COMMENT ON TABLE app.langsmith_deletion_requests IS
  'Durable LangSmith deletion *requests*. Success means the HTTP request was recorded, not that LangSmith deleted cloud traces.';

CREATE INDEX langsmith_deletion_due_idx
  ON app.langsmith_deletion_requests (status, retry_at)
  WHERE status IN ('pending', 'retrying');

ALTER TABLE app.langsmith_deletion_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.langsmith_deletion_requests FORCE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE app.langsmith_deletion_requests
  FROM PUBLIC, anon, authenticated, app_api;
GRANT SELECT, INSERT, UPDATE ON TABLE app.langsmith_deletion_requests TO app_worker;

CREATE POLICY langsmith_deletion_worker_rw
  ON app.langsmith_deletion_requests
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE TRIGGER langsmith_deletion_requests_touch_updated_at
  BEFORE UPDATE ON app.langsmith_deletion_requests
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

-- ---------------------------------------------------------------------------
-- Idempotency lookup that survives 7-day key NULL
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.find_run_for_idempotency(
  p_creator uuid,
  p_conversation uuid,
  p_key text
)
RETURNS SETOF app.runs
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
  SELECT r.*
  FROM app.runs AS r
  WHERE r.creator_user_id = p_creator
    AND r.conversation_id = p_conversation
    AND (
      r.idempotency_key = p_key
      OR r.idempotency_key_hash = encode(sha256(convert_to(p_key, 'UTF8')), 'hex')
    )
  ORDER BY (r.idempotency_key IS NOT NULL) DESC, r.created_at ASC
  LIMIT 1;
$fn$;

COMMENT ON FUNCTION app.find_run_for_idempotency(uuid, uuid, text) IS
  'Locate a paid run by live key or retained hash so reaping cannot double-charge.';

REVOKE ALL ON FUNCTION app.find_run_for_idempotency(uuid, uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.find_run_for_idempotency(uuid, uuid, text)
  TO app_api;

-- ---------------------------------------------------------------------------
-- Admit: reconnect via key or retained hash (one-paid-run after reaper)
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
  FROM app.find_run_for_idempotency(
    caller_user_id,
    p_conversation_id,
    p_idempotency_key
  );

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
      idempotency_key_hash,
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
      encode(sha256(convert_to(p_idempotency_key, 'UTF8')), 'hex'),
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
      FROM app.find_run_for_idempotency(
        caller_user_id,
        p_conversation_id,
        p_idempotency_key
      );
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

-- ---------------------------------------------------------------------------
-- Dedicated reaper: NOT budget true-up. Clock injectable via p_now.
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.reap_query_run_retention(
  p_now timestamptz DEFAULT timezone('utc', now())
)
RETURNS TABLE (
  keys_nulled bigint,
  events_deleted bigint,
  pending_keys_preserved bigint,
  true_up_invoked boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_keys bigint := 0;
  v_events bigint := 0;
  v_pending bigint := 0;
BEGIN
  -- Independent of app.true_up_query_reservation / true_up_query_reservation_internal.
  SELECT count(*)::bigint
  INTO v_pending
  FROM app.runs AS r
  WHERE r.status IN (
      'pending'::app.run_status,
      'running'::app.run_status
    )
    AND r.idempotency_key IS NOT NULL;

  UPDATE app.runs AS r
  SET idempotency_key = NULL
  WHERE r.status IN (
      'completed'::app.run_status,
      'failed'::app.run_status,
      'cancelled'::app.run_status,
      'partial'::app.run_status
    )
    AND r.idempotency_key IS NOT NULL
    AND COALESCE(r.completed_at, r.updated_at) <= (p_now - interval '7 days');

  GET DIAGNOSTICS v_keys = ROW_COUNT;

  DELETE FROM app.run_events AS e
  USING app.runs AS r
  WHERE e.run_id = r.id
    AND r.status IN (
      'completed'::app.run_status,
      'failed'::app.run_status,
      'cancelled'::app.run_status,
      'partial'::app.run_status
    )
    AND COALESCE(r.completed_at, r.updated_at) <= (p_now - interval '30 days');

  GET DIAGNOSTICS v_events = ROW_COUNT;

  keys_nulled := v_keys;
  events_deleted := v_events;
  pending_keys_preserved := v_pending;
  true_up_invoked := false;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.reap_query_run_retention(timestamptz) IS
  'NULL completed idempotency keys after 7 days and delete completed run_events after 30 days. Never touches pending/running keys. Never calls budget true-up.';

REVOKE ALL ON FUNCTION app.reap_query_run_retention(timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.reap_query_run_retention(timestamptz)
  TO app_worker, app_api;

CREATE OR REPLACE FUNCTION app.enqueue_query_maintenance_jobs(
  p_now timestamptz DEFAULT timezone('utc', now())
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_day text := to_char(p_now, 'YYYY-MM-DD');
  v_inserted integer := 0;
BEGIN
  INSERT INTO app.ingestion_jobs (
    job_kind,
    idempotency_key,
    payload_ref,
    priority,
    estimated_size_bytes
  )
  VALUES (
    'query_memory_reaper',
    'query_memory_reaper:' || v_day,
    jsonb_build_object('kind', 'query_memory_reaper', 'budget_true_up', false),
    'low'::app.job_priority,
    0
  )
  ON CONFLICT (idempotency_key) DO NOTHING;
  IF FOUND THEN
    v_inserted := v_inserted + 1;
  END IF;

  INSERT INTO app.ingestion_jobs (
    job_kind,
    idempotency_key,
    payload_ref,
    priority,
    estimated_size_bytes
  )
  VALUES (
    'langsmith_trace_deletion',
    'langsmith_trace_deletion:' || v_day,
    jsonb_build_object('kind', 'langsmith_trace_deletion', 'budget_true_up', false),
    'low'::app.job_priority,
    0
  )
  ON CONFLICT (idempotency_key) DO NOTHING;
  IF FOUND THEN
    v_inserted := v_inserted + 1;
  END IF;

  RETURN v_inserted;
END;
$fn$;

COMMENT ON FUNCTION app.enqueue_query_maintenance_jobs(timestamptz) IS
  'Idempotent daily enqueue of query_memory_reaper and langsmith_trace_deletion jobs. No budget reservation.';

REVOKE ALL ON FUNCTION app.enqueue_query_maintenance_jobs(timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.enqueue_query_maintenance_jobs(timestamptz)
  TO app_worker, app_api;

-- ---------------------------------------------------------------------------
-- Lingering-ID search after deletion (tombstone conversations row excluded)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.search_conversation_lingering_ids(
  p_conversation_id uuid
)
RETURNS TABLE (relation_name text, match_count bigint)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app, langgraph
AS $fn$
DECLARE
  v_id text := p_conversation_id::text;
BEGIN
  RETURN QUERY
  SELECT 'app.messages'::text, count(*)::bigint
  FROM app.messages
  WHERE conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.runs'::text, count(*)::bigint
  FROM app.runs
  WHERE conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.run_events'::text, count(*)::bigint
  FROM app.run_events AS e
  INNER JOIN app.runs AS r ON r.id = e.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.citations'::text, count(*)::bigint
  FROM app.citations AS c
  INNER JOIN app.runs AS r ON r.id = c.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.user_feedback'::text, count(*)::bigint
  FROM app.user_feedback AS f
  INNER JOIN app.runs AS r ON r.id = f.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'langgraph.checkpoints'::text, count(*)::bigint
  FROM langgraph.checkpoints
  WHERE thread_id = v_id
  UNION ALL
  SELECT 'langgraph.checkpoint_blobs'::text, count(*)::bigint
  FROM langgraph.checkpoint_blobs
  WHERE thread_id = v_id
  UNION ALL
  SELECT 'langgraph.checkpoint_writes'::text, count(*)::bigint
  FROM langgraph.checkpoint_writes
  WHERE thread_id = v_id
  UNION ALL
  SELECT 'langgraph.store'::text, count(*)::bigint
  FROM langgraph.store
  WHERE prefix LIKE '%.' || v_id
     OR prefix = v_id
     OR prefix LIKE v_id || '.%';
END;
$fn$;

COMMENT ON FUNCTION app.search_conversation_lingering_ids(uuid) IS
  'Count conversation-scoped rows that must be gone after immediate deletion. Tombstone conversations and content-free audit/usage are excluded.';

REVOKE ALL ON FUNCTION app.search_conversation_lingering_ids(uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.search_conversation_lingering_ids(uuid)
  TO app_api, app_worker;

-- ---------------------------------------------------------------------------
-- Immediate conversation deletion (one transaction)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.delete_conversation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app, langgraph
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
  v_id text;
  v_run_hashes text[] := '{}'::text[];
  v_now timestamptz := timezone('utc', now());
  v_role app.user_role;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id
    AND caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RETURN;
  END IF;

  v_id := p_conversation_id::text;
  v_role := caller_role::app.user_role;

  UPDATE app.conversations
  SET deleted_at = v_now
  WHERE id = p_conversation_id
    AND deleted_at IS NULL;

  SELECT coalesce(array_agg(encode(sha256(convert_to(r.id::text, 'UTF8')), 'hex')), '{}')
  INTO v_run_hashes
  FROM app.runs AS r
  WHERE r.conversation_id = p_conversation_id;

  DELETE FROM app.messages WHERE conversation_id = p_conversation_id;
  DELETE FROM app.user_feedback AS f
    USING app.runs AS r
    WHERE f.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.citations AS c
    USING app.runs AS r
    WHERE c.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.run_events AS e
    USING app.runs AS r
    WHERE e.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.runs WHERE conversation_id = p_conversation_id;

  DELETE FROM langgraph.checkpoint_writes WHERE thread_id = v_id;
  DELETE FROM langgraph.checkpoint_blobs WHERE thread_id = v_id;
  DELETE FROM langgraph.checkpoints WHERE thread_id = v_id;
  DELETE FROM langgraph.store
  WHERE prefix LIKE '%.' || v_id
     OR prefix = v_id
     OR prefix LIKE v_id || '.%';

  PERFORM app.append_audit_event(
    'conversation_deleted',
    caller_user_id,
    v_role,
    'conversation',
    p_conversation_id,
    caller_authorization_version,
    jsonb_build_object(
      'conversation_id', p_conversation_id,
      'run_id_hashes', to_jsonb(v_run_hashes),
      'audited_privileged', caller_role IN ('owner', 'admin')
        AND conversation_row.creator_user_id IS DISTINCT FROM caller_user_id
    )
  );

  INSERT INTO app.langsmith_deletion_requests (
    conversation_id_hash,
    run_id_hashes,
    hashed_trace_keys,
    status,
    sla_deadline_at,
    retry_at
  )
  VALUES (
    encode(sha256(convert_to(v_id, 'UTF8')), 'hex'),
    v_run_hashes,
    v_run_hashes,
    'pending',
    v_now + interval '24 hours',
    v_now
  );
END;
$fn$;

COMMENT ON FUNCTION app.delete_conversation(uuid, text, bigint, uuid) IS
  'Tombstone then purge conversation-scoped application, checkpoint, store, feedback, and event state. Content-free audit plus durable LangSmith deletion request.';

REVOKE ALL ON FUNCTION app.delete_conversation(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.delete_conversation(uuid, text, bigint, uuid)
  TO app_api;

-- Concurrent readers wait for the delete lock, then see the tombstone.
CREATE OR REPLACE FUNCTION app.get_conversation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid
)
RETURNS TABLE (
  id uuid,
  creator_user_id uuid,
  title text,
  created_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id
    AND (
      c.creator_user_id = caller_user_id
      OR caller_role IN ('owner', 'admin')
    )
  FOR SHARE;

  IF NOT FOUND OR conversation_row.deleted_at IS NOT NULL THEN
    RETURN;
  END IF;

  id := conversation_row.id;
  creator_user_id := conversation_row.creator_user_id;
  title := conversation_row.title;
  created_at := conversation_row.created_at;
  RETURN NEXT;
END;
$fn$;

-- ---------------------------------------------------------------------------
-- Feedback requires an exact tag. Citations expose source_unavailable.
-- ---------------------------------------------------------------------------

DROP FUNCTION IF EXISTS app.submit_run_feedback(
  uuid, text, bigint, uuid, smallint, text
);

CREATE OR REPLACE FUNCTION app.submit_run_feedback(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_rating smallint,
  p_comment text,
  p_tag text
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'feedback:authorization_rejected';
  END IF;

  IF p_rating IS NULL OR p_rating NOT IN (1, 5) THEN
    RAISE EXCEPTION 'feedback:invalid_rating';
  END IF;

  IF p_tag IS NULL OR p_tag NOT IN (
    'chunk/cleaning loss',
    'profile field wrong',
    'candidate miss',
    'wrong rerank',
    'bad refusal/overconfident answer',
    'missed relationship',
    'wrong route',
    'wrong calculation',
    'bad citation',
    'insufficient graph'
  ) THEN
    RAISE EXCEPTION 'feedback:invalid_tag';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.runs AS r
    INNER JOIN app.conversations AS c ON c.id = r.conversation_id
    WHERE r.id = p_run_id
      AND r.creator_user_id = caller_user_id
      AND c.deleted_at IS NULL
  ) THEN
    RAISE EXCEPTION 'feedback:not_found';
  END IF;

  INSERT INTO app.user_feedback (run_id, user_id, rating, comment, tag)
  VALUES (
    p_run_id,
    caller_user_id,
    p_rating,
    CASE
      WHEN p_comment IS NULL OR btrim(p_comment) = '' THEN NULL
      ELSE left(p_comment, 2000)
    END,
    p_tag
  )
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.submit_run_feedback(uuid, text, bigint, uuid, smallint, text, text) IS
  'Creator-only thumbs feedback with a required unmerged Phase 6 tag.';

REVOKE ALL ON FUNCTION app.submit_run_feedback(
  uuid, text, bigint, uuid, smallint, text, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.submit_run_feedback(
  uuid, text, bigint, uuid, smallint, text, text
) TO app_api;

DROP FUNCTION IF EXISTS app.list_run_citations(uuid, text, bigint, uuid);

CREATE OR REPLACE FUNCTION app.list_run_citations(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  citation_id uuid,
  citation_index integer,
  chunk_id uuid,
  provenance jsonb,
  source_unavailable boolean
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.runs AS r
    INNER JOIN app.conversations AS c ON c.id = r.conversation_id
    WHERE r.id = p_run_id
      AND r.creator_user_id = caller_user_id
      AND c.deleted_at IS NULL
  ) THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  RETURN QUERY
  SELECT
    ct.id,
    ct.citation_index,
    ct.chunk_id,
    ct.provenance,
    (
      ct.source_unavailable
      OR ct.chunk_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM app.document_chunks AS dc
        INNER JOIN app.documents AS d ON d.id = dc.document_id
        WHERE dc.id = ct.chunk_id
          AND d.deleted_at IS NULL
      )
    ) AS source_unavailable
  FROM app.citations AS ct
  WHERE ct.run_id = p_run_id
  ORDER BY ct.citation_index
  LIMIT 50;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid) IS
  'Creator-only citation identifiers. Deleted sources are flagged unavailable; messages are not rewritten.';

REVOKE ALL ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid)
  TO app_api;

-- ---------------------------------------------------------------------------
-- LangSmith deletion request claim / attempt recording
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.claim_langsmith_deletion_requests(
  p_now timestamptz DEFAULT timezone('utc', now()),
  p_limit integer DEFAULT 20
)
RETURNS SETOF app.langsmith_deletion_requests
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RETURN QUERY
  WITH due AS (
    SELECT q.id
    FROM app.langsmith_deletion_requests AS q
    WHERE q.status IN ('pending', 'retrying')
      AND q.retry_at <= p_now
      AND q.attempts < q.max_attempts
    ORDER BY q.retry_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT p_limit
  )
  UPDATE app.langsmith_deletion_requests AS r
  SET
    status = CASE
      WHEN p_now >= r.sla_deadline_at THEN 'sla_expired'
      ELSE 'retrying'
    END,
    attempts = r.attempts + 1,
    retry_at = p_now + make_interval(mins => least(60, greatest(1, r.attempts + 1)))
  FROM due
  WHERE r.id = due.id
  RETURNING r.*;
END;
$fn$;

COMMENT ON FUNCTION app.claim_langsmith_deletion_requests(timestamptz, integer) IS
  'Claim due LangSmith deletion request rows. SLA expiry is recorded at 24h; cloud deletion is not asserted.';

REVOKE ALL ON FUNCTION app.claim_langsmith_deletion_requests(timestamptz, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.claim_langsmith_deletion_requests(timestamptz, integer)
  TO app_worker, app_api;

CREATE OR REPLACE FUNCTION app.record_langsmith_deletion_attempt(
  p_id uuid,
  p_success boolean,
  p_error text DEFAULT NULL,
  p_now timestamptz DEFAULT timezone('utc', now())
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  UPDATE app.langsmith_deletion_requests
  SET
    status = CASE
      WHEN p_success THEN 'request_recorded'
      WHEN p_now >= sla_deadline_at THEN 'sla_expired'
      ELSE 'retrying'
    END,
    request_recorded_at = CASE WHEN p_success THEN p_now ELSE request_recorded_at END,
    last_error = CASE
      WHEN p_success THEN NULL
      ELSE left(coalesce(p_error, 'request_failed'), 500)
    END
  WHERE id = p_id;
END;
$fn$;

COMMENT ON FUNCTION app.record_langsmith_deletion_attempt(uuid, boolean, text, timestamptz) IS
  'Record one LangSmith deletion HTTP attempt. request_recorded means the request was sent, not that traces were deleted.';

REVOKE ALL ON FUNCTION app.record_langsmith_deletion_attempt(uuid, boolean, text, timestamptz)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.record_langsmith_deletion_attempt(uuid, boolean, text, timestamptz)
  TO app_worker, app_api;
