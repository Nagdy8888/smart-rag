-- Durable exam runs, count-only results/reports, and hidden evaluation
-- conversations. Owner/admin app_api RPCs only. Holdout stays closed.
-- Browser conversation RPCs never return purpose=evaluation.

ALTER TABLE app.conversations
  ADD COLUMN IF NOT EXISTS purpose text NOT NULL DEFAULT 'chat';

ALTER TABLE app.conversations
  DROP CONSTRAINT IF EXISTS conversations_purpose_chk;

ALTER TABLE app.conversations
  ADD CONSTRAINT conversations_purpose_chk
  CHECK (purpose IN ('chat', 'evaluation'));

COMMENT ON COLUMN app.conversations.purpose IS
  'chat is browser-visible. evaluation is exam-admission only and never listed.';

CREATE TABLE app.eval_exam_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  creator_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  conversation_id uuid NOT NULL REFERENCES app.conversations (id) ON DELETE RESTRICT,
  split text NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  dataset_hash text NOT NULL,
  candidate_fingerprint text NOT NULL,
  metric_version text NOT NULL,
  cache_mode text NOT NULL,
  holdout_opened boolean NOT NULL DEFAULT false,
  case_ids uuid[] NOT NULL,
  case_count integer NOT NULL,
  completed_case_count integer NOT NULL DEFAULT 0,
  idempotency_key text NOT NULL,
  request_payload_hash text NOT NULL,
  lease_owner text,
  lease_expires_at timestamptz,
  error_code text,
  expires_at timestamptz NOT NULL,
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT eval_exam_runs_split_chk CHECK (split IN ('development', 'qualification')),
  CONSTRAINT eval_exam_runs_status_chk CHECK (
    status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')
  ),
  CONSTRAINT eval_exam_runs_metric_chk CHECK (
    metric_version = 'production_corpus_all_required_gold_at_10_v1'
  ),
  CONSTRAINT eval_exam_runs_cache_chk CHECK (cache_mode = 'cold_bypass'),
  CONSTRAINT eval_exam_runs_holdout_chk CHECK (holdout_opened IS FALSE),
  CONSTRAINT eval_exam_runs_hash_chk CHECK (dataset_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT eval_exam_runs_payload_hash_chk CHECK (
    request_payload_hash ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT eval_exam_runs_fingerprint_chk CHECK (
    char_length(candidate_fingerprint) BETWEEN 8 AND 128
  ),
  CONSTRAINT eval_exam_runs_idempotency_chk CHECK (
    char_length(idempotency_key) BETWEEN 8 AND 128
  ),
  CONSTRAINT eval_exam_runs_case_count_chk CHECK (
    case_count BETWEEN 1 AND 60
    AND case_count = cardinality(case_ids)
    AND completed_case_count >= 0
    AND completed_case_count <= case_count
  ),
  CONSTRAINT eval_exam_runs_creator_idempotency_uq UNIQUE (
    creator_user_id,
    idempotency_key
  )
);

COMMENT ON TABLE app.eval_exam_runs IS
  'Durable Hybrid exam jobs. One queued/running exam. 365-day expiry. No question text.';

CREATE TABLE app.eval_exam_case_results (
  exam_run_id uuid NOT NULL REFERENCES app.eval_exam_runs (id) ON DELETE CASCADE,
  case_id uuid NOT NULL REFERENCES app.eval_quiz_cases (id) ON DELETE RESTRICT,
  ordinal integer NOT NULL,
  hit boolean NOT NULL,
  gold_count integer NOT NULL,
  ranked_hit_count integer NOT NULL,
  latency_ms integer,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT eval_exam_case_results_pk PRIMARY KEY (exam_run_id, case_id),
  CONSTRAINT eval_exam_case_results_ordinal_chk CHECK (ordinal >= 1),
  CONSTRAINT eval_exam_case_results_gold_chk CHECK (gold_count BETWEEN 1 AND 3),
  CONSTRAINT eval_exam_case_results_hit_count_chk CHECK (
    ranked_hit_count BETWEEN 0 AND gold_count
  )
);

COMMENT ON TABLE app.eval_exam_case_results IS
  'Count-only per-case Hybrid Recall@10. No questions, excerpts, ranked IDs, or gold UUID lists.';

CREATE TABLE app.eval_exam_reports (
  exam_run_id uuid PRIMARY KEY REFERENCES app.eval_exam_runs (id) ON DELETE CASCADE,
  split text NOT NULL,
  dataset_hash text NOT NULL,
  candidate_fingerprint text NOT NULL,
  metric_version text NOT NULL,
  case_count integer NOT NULL,
  hit_count integer NOT NULL,
  hybrid_recall_at_10 numeric(6, 4) NOT NULL,
  gates_pass boolean NOT NULL,
  holdout_opened boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT eval_exam_reports_split_chk CHECK (split IN ('development', 'qualification')),
  CONSTRAINT eval_exam_reports_metric_chk CHECK (
    metric_version = 'production_corpus_all_required_gold_at_10_v1'
  ),
  CONSTRAINT eval_exam_reports_holdout_chk CHECK (holdout_opened IS FALSE),
  CONSTRAINT eval_exam_reports_counts_chk CHECK (
    case_count BETWEEN 1 AND 60
    AND hit_count >= 0
    AND hit_count <= case_count
  )
);

COMMENT ON TABLE app.eval_exam_reports IS
  'Immutable successful exam reports. Count-only. Partial/failed/cancelled runs never appear.';

CREATE UNIQUE INDEX eval_exam_runs_one_active_uq
  ON app.eval_exam_runs ((true))
  WHERE status IN ('queued', 'running');

CREATE UNIQUE INDEX eval_exam_runs_qualification_key_uq
  ON app.eval_exam_runs (dataset_hash, candidate_fingerprint)
  WHERE split = 'qualification'
    AND status IN ('queued', 'running', 'succeeded', 'failed');

CREATE INDEX eval_exam_runs_expires_idx
  ON app.eval_exam_runs (expires_at);

CREATE INDEX eval_exam_runs_claim_idx
  ON app.eval_exam_runs (status, lease_expires_at, created_at);

CREATE TRIGGER eval_exam_runs_touch_updated_at
  BEFORE UPDATE ON app.eval_exam_runs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE OR REPLACE FUNCTION app.eval_exam_reports_protect()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    RAISE EXCEPTION 'eval_exam:report_immutable';
  END IF;
  IF TG_OP = 'DELETE'
    AND current_setting('app.eval_exam_purge', true) IS DISTINCT FROM '1' THEN
    RAISE EXCEPTION 'eval_exam:report_immutable';
  END IF;
  RETURN OLD;
END;
$fn$;

CREATE TRIGGER eval_exam_reports_protect
  BEFORE UPDATE OR DELETE ON app.eval_exam_reports
  FOR EACH ROW
  EXECUTE FUNCTION app.eval_exam_reports_protect();

ALTER TABLE app.eval_exam_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.eval_exam_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.eval_exam_case_results ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.eval_exam_case_results FORCE ROW LEVEL SECURITY;
ALTER TABLE app.eval_exam_reports ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.eval_exam_reports FORCE ROW LEVEL SECURITY;

CREATE POLICY eval_exam_runs_postgres_all
  ON app.eval_exam_runs
  FOR ALL
  TO postgres
  USING (true)
  WITH CHECK (true);

CREATE POLICY eval_exam_case_results_postgres_all
  ON app.eval_exam_case_results
  FOR ALL
  TO postgres
  USING (true)
  WITH CHECK (true);

CREATE POLICY eval_exam_reports_postgres_all
  ON app.eval_exam_reports
  FOR ALL
  TO postgres
  USING (true)
  WITH CHECK (true);

REVOKE ALL ON TABLE app.eval_exam_runs FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON TABLE app.eval_exam_case_results FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON TABLE app.eval_exam_reports FROM PUBLIC, anon, authenticated, app_api, app_worker;
GRANT ALL ON TABLE app.eval_exam_runs TO postgres;
GRANT ALL ON TABLE app.eval_exam_case_results TO postgres;
GRANT ALL ON TABLE app.eval_exam_reports TO postgres;

CREATE OR REPLACE FUNCTION app._eval_exam_require_owner_admin(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS void
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
END;
$fn$;

CREATE OR REPLACE FUNCTION app._eval_exam_audit(
  p_event_type text,
  p_actor_user_id uuid,
  p_actor_role text,
  p_target_id uuid,
  p_authorization_version bigint,
  p_payload jsonb
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RETURN app.append_audit_event(
    p_event_type,
    p_actor_user_id,
    p_actor_role::app.user_role,
    'eval_exam_run',
    p_target_id,
    p_authorization_version,
    COALESCE(p_payload, '{}'::jsonb)
  );
END;
$fn$;

CREATE OR REPLACE FUNCTION app._eval_exam_snapshot(
  caller_user_id uuid,
  caller_role text,
  p_split text
)
RETURNS TABLE (
  case_ids uuid[],
  dataset_hash text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app, extensions
AS $fn$
DECLARE
  v_ids uuid[];
  v_case uuid;
  v_gold integer;
  v_canonical text := '';
  v_chunk uuid;
BEGIN
  SELECT coalesce(array_agg(c.id ORDER BY c.created_at, c.id), '{}'::uuid[])
  INTO v_ids
  FROM app.eval_quiz_cases AS c
  WHERE c.split = p_split
    AND c.review_status = 'approved'
    AND c.expires_at > timezone('utc', now());

  IF cardinality(v_ids) < 1 THEN
    RAISE EXCEPTION 'eval_exam:empty_dataset';
  END IF;

  FOREACH v_case IN ARRAY v_ids LOOP
    SELECT count(*)::integer INTO v_gold
    FROM app.eval_quiz_gold_chunks AS g
    WHERE g.case_id = v_case;
    IF v_gold < 1 OR v_gold > 3 THEN
      RAISE EXCEPTION 'eval_exam:gold_required';
    END IF;
    FOR v_chunk IN
      SELECT g.chunk_id
      FROM app.eval_quiz_gold_chunks AS g
      WHERE g.case_id = v_case
      ORDER BY g.ordinal
    LOOP
      IF NOT app._eval_quiz_chunk_is_current(caller_user_id, caller_role, v_chunk) THEN
        RAISE EXCEPTION 'eval_exam:gold_stale';
      END IF;
    END LOOP;
    v_canonical := v_canonical || v_case::text || ':' || (
      SELECT string_agg(g.chunk_id::text, ',' ORDER BY g.ordinal)
      FROM app.eval_quiz_gold_chunks AS g
      WHERE g.case_id = v_case
    ) || '|';
  END LOOP;

  case_ids := v_ids;
  dataset_hash := encode(sha256(convert_to(v_canonical, 'UTF8')), 'hex');
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.enqueue_eval_exam(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_split text,
  p_idempotency_key text,
  p_request_payload_hash text,
  p_candidate_fingerprint text,
  p_expected_dataset_hash text
)
RETURNS TABLE (
  exam_run_id uuid,
  status text,
  dataset_hash text,
  conversation_id uuid,
  replayed boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app, extensions
AS $fn$
DECLARE
  v_split text;
  v_existing app.eval_exam_runs%ROWTYPE;
  v_active app.eval_exam_runs%ROWTYPE;
  v_snap record;
  v_conversation uuid;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  v_split := lower(btrim(p_split));
  IF v_split = 'holdout' THEN
    RAISE EXCEPTION 'eval_exam:holdout_rejected';
  END IF;
  IF v_split NOT IN ('development', 'qualification') THEN
    RAISE EXCEPTION 'eval_exam:split_invalid';
  END IF;
  IF p_idempotency_key IS NULL
    OR char_length(p_idempotency_key) < 8
    OR char_length(p_idempotency_key) > 128 THEN
    RAISE EXCEPTION 'eval_exam:idempotency_invalid';
  END IF;
  IF p_request_payload_hash IS NULL
    OR p_request_payload_hash !~ '^[0-9a-f]{64}$' THEN
    RAISE EXCEPTION 'eval_exam:payload_hash_invalid';
  END IF;
  IF p_candidate_fingerprint IS NULL
    OR char_length(p_candidate_fingerprint) < 8
    OR char_length(p_candidate_fingerprint) > 128 THEN
    RAISE EXCEPTION 'eval_exam:fingerprint_invalid';
  END IF;

  PERFORM app._eval_quiz_lock_workspace();

  SELECT * INTO v_existing
  FROM app.eval_exam_runs AS e
  WHERE e.creator_user_id = caller_user_id
    AND e.idempotency_key = p_idempotency_key;

  IF FOUND THEN
    IF v_existing.request_payload_hash IS DISTINCT FROM p_request_payload_hash THEN
      RAISE EXCEPTION 'eval_exam:idempotency_collision';
    END IF;
    exam_run_id := v_existing.id;
    status := v_existing.status;
    dataset_hash := v_existing.dataset_hash;
    conversation_id := v_existing.conversation_id;
    replayed := true;
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT * INTO v_snap
  FROM app._eval_exam_snapshot(caller_user_id, caller_role, v_split);

  IF p_expected_dataset_hash IS NOT NULL
    AND p_expected_dataset_hash IS DISTINCT FROM v_snap.dataset_hash THEN
    RAISE EXCEPTION 'eval_exam:stale_dataset_hash';
  END IF;

  SELECT * INTO v_active
  FROM app.eval_exam_runs AS e
  WHERE e.status IN ('queued', 'running')
  FOR UPDATE;

  IF FOUND THEN
    RAISE EXCEPTION 'eval_exam:already_running';
  END IF;

  IF v_split = 'qualification' AND EXISTS (
    SELECT 1
    FROM app.eval_exam_runs AS e
    WHERE e.split = 'qualification'
      AND e.dataset_hash = v_snap.dataset_hash
      AND e.candidate_fingerprint = p_candidate_fingerprint
      AND (
        e.status IN ('queued', 'running', 'succeeded', 'failed')
        OR EXISTS (
          SELECT 1
          FROM app.eval_exam_case_results AS r
          WHERE r.exam_run_id = e.id
        )
      )
  ) THEN
    RAISE EXCEPTION 'eval_exam:qualification_consumed';
  END IF;

  INSERT INTO app.conversations (creator_user_id, title, purpose)
  VALUES (caller_user_id, NULL, 'evaluation')
  RETURNING id INTO v_conversation;

  BEGIN
    INSERT INTO app.eval_exam_runs (
      creator_user_id,
      conversation_id,
      split,
      status,
      dataset_hash,
      candidate_fingerprint,
      metric_version,
      cache_mode,
      holdout_opened,
      case_ids,
      case_count,
      idempotency_key,
      request_payload_hash,
      expires_at
    )
    VALUES (
      caller_user_id,
      v_conversation,
      v_split,
      'queued',
      v_snap.dataset_hash,
      p_candidate_fingerprint,
      'production_corpus_all_required_gold_at_10_v1',
      'cold_bypass',
      false,
      v_snap.case_ids,
      cardinality(v_snap.case_ids),
      p_idempotency_key,
      p_request_payload_hash,
      timezone('utc', now()) + interval '365 days'
    )
    RETURNING
      app.eval_exam_runs.id,
      app.eval_exam_runs.status,
      app.eval_exam_runs.dataset_hash,
      app.eval_exam_runs.conversation_id
    INTO exam_run_id, status, dataset_hash, conversation_id;
  EXCEPTION
    WHEN unique_violation THEN
      RAISE EXCEPTION 'eval_exam:already_running';
  END;

  replayed := false;
  PERFORM app._eval_exam_audit(
    'eval_exam_enqueued',
    caller_user_id,
    caller_role,
    exam_run_id,
    caller_authorization_version,
    jsonb_build_object(
      'split', v_split,
      'case_count', cardinality(v_snap.case_ids)
    )
  );
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.claim_eval_exam(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_lease_owner text,
  p_lease_seconds integer
)
RETURNS TABLE (
  exam_run_id uuid,
  conversation_id uuid,
  split text,
  dataset_hash text,
  candidate_fingerprint text,
  case_ids uuid[],
  case_count integer,
  completed_case_count integer
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_lease integer;
  v_row app.eval_exam_runs%ROWTYPE;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  IF p_lease_owner IS NULL OR char_length(p_lease_owner) < 8 THEN
    RAISE EXCEPTION 'eval_exam:lease_owner_invalid';
  END IF;
  v_lease := LEAST(GREATEST(COALESCE(p_lease_seconds, 30), 5), 60);

  SELECT * INTO v_row
  FROM app.eval_exam_runs AS e
  WHERE e.status = 'queued'
     OR (
       e.status = 'running'
       AND e.lease_expires_at IS NOT NULL
       AND e.lease_expires_at < v_now
     )
  ORDER BY e.created_at ASC, e.id ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF NOT FOUND THEN
    RETURN;
  END IF;

  UPDATE app.eval_exam_runs AS e
  SET
    status = 'running',
    lease_owner = p_lease_owner,
    lease_expires_at = v_now + make_interval(secs => v_lease),
    started_at = COALESCE(e.started_at, v_now)
  WHERE e.id = v_row.id
  RETURNING * INTO v_row;

  exam_run_id := v_row.id;
  conversation_id := v_row.conversation_id;
  split := v_row.split;
  dataset_hash := v_row.dataset_hash;
  candidate_fingerprint := v_row.candidate_fingerprint;
  case_ids := v_row.case_ids;
  case_count := v_row.case_count;
  completed_case_count := v_row.completed_case_count;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.heartbeat_eval_exam(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid,
  p_lease_owner text,
  p_lease_seconds integer
)
RETURNS timestamptz
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_lease integer;
  v_expires timestamptz;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  v_lease := LEAST(GREATEST(COALESCE(p_lease_seconds, 30), 5), 60);

  UPDATE app.eval_exam_runs AS e
  SET lease_expires_at = v_now + make_interval(secs => v_lease)
  WHERE e.id = p_exam_run_id
    AND e.status = 'running'
    AND e.lease_owner = p_lease_owner
    AND e.lease_expires_at IS NOT NULL
    AND e.lease_expires_at >= v_now
  RETURNING e.lease_expires_at INTO v_expires;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_exam:lease_not_held';
  END IF;
  RETURN v_expires;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.reclaim_eval_exam(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid,
  p_lease_owner text,
  p_lease_seconds integer
)
RETURNS TABLE (
  exam_run_id uuid,
  reclaimed boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_lease integer;
  v_row app.eval_exam_runs%ROWTYPE;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  v_lease := LEAST(GREATEST(COALESCE(p_lease_seconds, 30), 5), 60);

  SELECT * INTO v_row
  FROM app.eval_exam_runs AS e
  WHERE e.id = p_exam_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_exam:not_found';
  END IF;
  IF v_row.status <> 'running' THEN
    RAISE EXCEPTION 'eval_exam:not_running';
  END IF;
  IF v_row.lease_expires_at IS NOT NULL AND v_row.lease_expires_at >= v_now THEN
    RAISE EXCEPTION 'eval_exam:lease_live';
  END IF;

  UPDATE app.eval_exam_runs AS e
  SET
    lease_owner = p_lease_owner,
    lease_expires_at = v_now + make_interval(secs => v_lease)
  WHERE e.id = p_exam_run_id;

  exam_run_id := p_exam_run_id;
  reclaimed := true;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.persist_eval_exam_case_result(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid,
  p_case_id uuid,
  p_hit boolean,
  p_gold_count integer,
  p_ranked_hit_count integer,
  p_latency_ms integer
)
RETURNS TABLE (
  exam_run_id uuid,
  case_id uuid,
  inserted boolean,
  completed_case_count integer
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_row app.eval_exam_runs%ROWTYPE;
  v_ordinal integer;
  v_inserted uuid;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );

  SELECT * INTO v_row
  FROM app.eval_exam_runs AS e
  WHERE e.id = p_exam_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_exam:not_found';
  END IF;
  IF v_row.status NOT IN ('queued', 'running') THEN
    RAISE EXCEPTION 'eval_exam:not_running';
  END IF;

  v_ordinal := array_position(v_row.case_ids, p_case_id);
  IF v_ordinal IS NULL THEN
    RAISE EXCEPTION 'eval_exam:case_not_in_snapshot';
  END IF;
  IF p_gold_count IS NULL OR p_gold_count < 1 OR p_gold_count > 3 THEN
    RAISE EXCEPTION 'eval_exam:gold_count_invalid';
  END IF;
  IF p_ranked_hit_count IS NULL
    OR p_ranked_hit_count < 0
    OR p_ranked_hit_count > p_gold_count THEN
    RAISE EXCEPTION 'eval_exam:hit_count_invalid';
  END IF;

  INSERT INTO app.eval_exam_case_results (
    exam_run_id,
    case_id,
    ordinal,
    hit,
    gold_count,
    ranked_hit_count,
    latency_ms
  )
  VALUES (
    p_exam_run_id,
    p_case_id,
    v_ordinal,
    COALESCE(p_hit, false),
    p_gold_count,
    p_ranked_hit_count,
    p_latency_ms
  )
  ON CONFLICT (exam_run_id, case_id) DO NOTHING
  RETURNING app.eval_exam_case_results.case_id INTO v_inserted;

  IF v_inserted IS NOT NULL THEN
    UPDATE app.eval_exam_runs AS e
    SET completed_case_count = e.completed_case_count + 1
    WHERE e.id = p_exam_run_id
    RETURNING e.completed_case_count INTO completed_case_count;
    inserted := true;
  ELSE
    SELECT e.completed_case_count
    INTO completed_case_count
    FROM app.eval_exam_runs AS e
    WHERE e.id = p_exam_run_id;
    inserted := false;
  END IF;

  exam_run_id := p_exam_run_id;
  case_id := p_case_id;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.finalize_eval_exam(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid,
  p_gates_pass boolean,
  p_error_code text
)
RETURNS TABLE (
  exam_run_id uuid,
  status text,
  report_present boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_row app.eval_exam_runs%ROWTYPE;
  v_hits integer;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );

  SELECT * INTO v_row
  FROM app.eval_exam_runs AS e
  WHERE e.id = p_exam_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_exam:not_found';
  END IF;
  IF v_row.status IN ('succeeded', 'failed', 'cancelled') THEN
    exam_run_id := v_row.id;
    status := v_row.status;
    report_present := EXISTS (
      SELECT 1 FROM app.eval_exam_reports AS r WHERE r.exam_run_id = v_row.id
    );
    RETURN NEXT;
    RETURN;
  END IF;

  IF p_error_code IS NOT NULL AND btrim(p_error_code) <> '' THEN
    UPDATE app.eval_exam_runs AS e
    SET
      status = 'failed',
      error_code = left(btrim(p_error_code), 64),
      lease_owner = NULL,
      lease_expires_at = NULL,
      completed_at = timezone('utc', now())
    WHERE e.id = p_exam_run_id;
    PERFORM app._eval_exam_audit(
      'eval_exam_failed',
      caller_user_id,
      caller_role,
      p_exam_run_id,
      caller_authorization_version,
      jsonb_build_object('error_code', left(btrim(p_error_code), 64))
    );
    exam_run_id := p_exam_run_id;
    status := 'failed';
    report_present := false;
    RETURN NEXT;
    RETURN;
  END IF;

  IF v_row.completed_case_count <> v_row.case_count THEN
    RAISE EXCEPTION 'eval_exam:incomplete';
  END IF;

  SELECT count(*) FILTER (WHERE r.hit)::integer
  INTO v_hits
  FROM app.eval_exam_case_results AS r
  WHERE r.exam_run_id = p_exam_run_id;

  INSERT INTO app.eval_exam_reports (
    exam_run_id,
    split,
    dataset_hash,
    candidate_fingerprint,
    metric_version,
    case_count,
    hit_count,
    hybrid_recall_at_10,
    gates_pass,
    holdout_opened
  )
  VALUES (
    p_exam_run_id,
    v_row.split,
    v_row.dataset_hash,
    v_row.candidate_fingerprint,
    v_row.metric_version,
    v_row.case_count,
    v_hits,
    (v_hits::numeric / v_row.case_count),
    COALESCE(p_gates_pass, false),
    false
  );

  UPDATE app.eval_exam_runs AS e
  SET
    status = 'succeeded',
    lease_owner = NULL,
    lease_expires_at = NULL,
    completed_at = timezone('utc', now())
  WHERE e.id = p_exam_run_id;

  PERFORM app._eval_exam_audit(
    'eval_exam_finalized',
    caller_user_id,
    caller_role,
    p_exam_run_id,
    caller_authorization_version,
    jsonb_build_object(
      'case_count', v_row.case_count,
      'hit_count', v_hits
    )
  );

  exam_run_id := p_exam_run_id;
  status := 'succeeded';
  report_present := true;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.cancel_eval_exam(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid
)
RETURNS TABLE (
  exam_run_id uuid,
  status text
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_row app.eval_exam_runs%ROWTYPE;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );

  SELECT * INTO v_row
  FROM app.eval_exam_runs AS e
  WHERE e.id = p_exam_run_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_exam:not_found';
  END IF;
  IF v_row.status IN ('succeeded', 'failed', 'cancelled') THEN
    exam_run_id := v_row.id;
    status := v_row.status;
    RETURN NEXT;
    RETURN;
  END IF;

  UPDATE app.eval_exam_runs AS e
  SET
    status = 'cancelled',
    lease_owner = NULL,
    lease_expires_at = NULL,
    completed_at = timezone('utc', now())
  WHERE e.id = p_exam_run_id;

  PERFORM app._eval_exam_audit(
    'eval_exam_cancelled',
    caller_user_id,
    caller_role,
    p_exam_run_id,
    caller_authorization_version,
    '{}'::jsonb
  );
  exam_run_id := p_exam_run_id;
  status := 'cancelled';
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.get_eval_exam_run(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_exam_run_id uuid
)
RETURNS TABLE (
  exam_run_id uuid,
  split text,
  status text,
  dataset_hash text,
  candidate_fingerprint text,
  case_count integer,
  completed_case_count integer,
  holdout_opened boolean,
  conversation_id uuid
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  RETURN QUERY
  SELECT
    e.id,
    e.split,
    e.status,
    e.dataset_hash,
    e.candidate_fingerprint,
    e.case_count,
    e.completed_case_count,
    e.holdout_opened,
    e.conversation_id
  FROM app.eval_exam_runs AS e
  WHERE e.id = p_exam_run_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.get_latest_eval_exam_report(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  exam_run_id uuid,
  split text,
  dataset_hash text,
  case_count integer,
  hit_count integer,
  hybrid_recall_at_10 numeric,
  gates_pass boolean,
  holdout_opened boolean,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  RETURN QUERY
  SELECT
    r.exam_run_id,
    r.split,
    r.dataset_hash,
    r.case_count,
    r.hit_count,
    r.hybrid_recall_at_10,
    r.gates_pass,
    r.holdout_opened,
    r.created_at
  FROM app.eval_exam_reports AS r
  INNER JOIN app.eval_exam_runs AS e ON e.id = r.exam_run_id
  WHERE e.status = 'succeeded'
  ORDER BY r.created_at DESC, r.exam_run_id DESC
  LIMIT 1;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.purge_expired_eval_exam_runs(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_count integer;
BEGIN
  PERFORM app._eval_exam_require_owner_admin(
    caller_user_id,
    caller_role,
    caller_authorization_version
  );
  PERFORM set_config('app.eval_exam_purge', '1', true);
  DELETE FROM app.eval_exam_runs AS e
  WHERE e.expires_at < timezone('utc', now())
    AND e.status IN ('succeeded', 'failed', 'cancelled');
  GET DIAGNOSTICS v_count = ROW_COUNT;
  PERFORM app._eval_exam_audit(
    'eval_exam_purged',
    caller_user_id,
    caller_role,
    '00000000-0000-0000-0000-000000000001'::uuid,
    caller_authorization_version,
    jsonb_build_object('purged_count', v_count)
  );
  RETURN v_count;
END;
$fn$;

-- Browser conversation RPCs: hide evaluation purpose without schema changes.

CREATE OR REPLACE FUNCTION app.create_conversation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_title text
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
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  INSERT INTO app.conversations (creator_user_id, title, purpose)
  VALUES (
    caller_user_id,
    CASE
      WHEN p_title IS NULL OR btrim(p_title) = '' THEN NULL
      ELSE left(p_title, 512)
    END,
    'chat'
  )
  RETURNING
    app.conversations.id,
    app.conversations.creator_user_id,
    app.conversations.title,
    app.conversations.created_at
  INTO id, creator_user_id, title, created_at;

  RETURN NEXT;
END;
$fn$;

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
    AND c.purpose = 'chat'
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

CREATE OR REPLACE FUNCTION app.list_user_conversations_page(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_limit integer DEFAULT 50,
  p_cursor_created_at timestamptz DEFAULT NULL,
  p_cursor_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  creator_user_id uuid,
  title text,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  capped_limit integer;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  IF (p_cursor_created_at IS NULL) <> (p_cursor_id IS NULL) THEN
    RAISE EXCEPTION 'conversation:invalid_cursor';
  END IF;

  capped_limit := GREATEST(1, LEAST(COALESCE(p_limit, 50), 200));

  RETURN QUERY
  SELECT c.id, c.creator_user_id, c.title, c.created_at
  FROM app.conversations AS c
  WHERE c.deleted_at IS NULL
    AND c.purpose = 'chat'
    AND (
      c.creator_user_id = caller_user_id
      OR caller_role IN ('owner', 'admin')
    )
    AND (
      p_cursor_created_at IS NULL
      OR (c.created_at, c.id) < (p_cursor_created_at, p_cursor_id)
    )
  ORDER BY c.created_at DESC, c.id DESC
  LIMIT capped_limit;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.list_conversation_messages(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_limit integer DEFAULT 50,
  p_before_id uuid DEFAULT NULL
)
RETURNS TABLE (
  message_id uuid,
  role text,
  content text,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
  bounded_limit integer;
  cursor_created_at timestamptz;
  cursor_id uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_memory:authorization_rejected';
  END IF;

  IF p_conversation_id IS NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  bounded_limit := LEAST(GREATEST(COALESCE(p_limit, 50), 1), 100);

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id;

  IF NOT FOUND OR conversation_row.purpose IS DISTINCT FROM 'chat' THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_deleted';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_memory:conversation_forbidden';
  END IF;

  IF p_before_id IS NOT NULL THEN
    SELECT m.created_at, m.id
    INTO cursor_created_at, cursor_id
    FROM app.messages AS m
    WHERE m.id = p_before_id
      AND m.conversation_id = p_conversation_id;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'query_memory:conversation_not_found';
    END IF;
  END IF;

  RETURN QUERY
  SELECT
    m.id,
    m.role,
    m.content,
    m.created_at
  FROM app.messages AS m
  WHERE m.conversation_id = p_conversation_id
    AND m.role IN ('user', 'assistant')
    AND (
      p_before_id IS NULL
      OR (m.created_at, m.id) < (cursor_created_at, cursor_id)
    )
  ORDER BY m.created_at DESC, m.id DESC
  LIMIT bounded_limit;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.get_conversation_title_source(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid
)
RETURNS TABLE (
  current_title text,
  user_excerpt text,
  assistant_excerpt text
)
LANGUAGE plpgsql
STABLE
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

  IF p_conversation_id IS NULL THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id;

  IF NOT FOUND
    OR conversation_row.purpose IS DISTINCT FROM 'chat' THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  RETURN QUERY
  SELECT
    conversation_row.title,
    (
      SELECT left(m.content, 2000)
      FROM app.messages AS m
      WHERE m.conversation_id = p_conversation_id
        AND m.role = 'user'
      ORDER BY m.created_at ASC, m.id ASC
      LIMIT 1
    ),
    (
      SELECT left(m.content, 2000)
      FROM app.messages AS m
      WHERE m.conversation_id = p_conversation_id
        AND m.role = 'assistant'
      ORDER BY m.created_at ASC, m.id ASC
      LIMIT 1
    );
END;
$fn$;

CREATE OR REPLACE FUNCTION app.update_conversation_title(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_title text
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
  safe_title text;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  IF p_conversation_id IS NULL THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id
  FOR UPDATE;

  IF NOT FOUND
    OR conversation_row.purpose IS DISTINCT FROM 'chat' THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  safe_title := CASE
    WHEN p_title IS NULL OR btrim(p_title) = '' THEN NULL
    ELSE left(btrim(p_title), 512)
  END;

  UPDATE app.conversations AS c
  SET title = safe_title
  WHERE c.id = p_conversation_id
    AND c.deleted_at IS NULL
    AND c.purpose = 'chat'
  RETURNING
    c.id,
    c.creator_user_id,
    c.title,
    c.created_at
  INTO id, creator_user_id, title, created_at;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  RETURN NEXT;
END;
$fn$;

REVOKE ALL ON FUNCTION app._eval_exam_require_owner_admin(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_exam_audit(text, uuid, text, uuid, bigint, jsonb)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_exam_snapshot(uuid, text, text)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app.eval_exam_reports_protect()
  FROM PUBLIC, anon, authenticated, app_api, app_worker;

REVOKE ALL ON FUNCTION app.enqueue_eval_exam(
  uuid, text, bigint, text, text, text, text, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.enqueue_eval_exam(
  uuid, text, bigint, text, text, text, text, text
) TO app_api;

REVOKE ALL ON FUNCTION app.claim_eval_exam(
  uuid, text, bigint, text, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.claim_eval_exam(
  uuid, text, bigint, text, integer
) TO app_api;

REVOKE ALL ON FUNCTION app.heartbeat_eval_exam(
  uuid, text, bigint, uuid, text, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.heartbeat_eval_exam(
  uuid, text, bigint, uuid, text, integer
) TO app_api;

REVOKE ALL ON FUNCTION app.reclaim_eval_exam(
  uuid, text, bigint, uuid, text, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.reclaim_eval_exam(
  uuid, text, bigint, uuid, text, integer
) TO app_api;

REVOKE ALL ON FUNCTION app.persist_eval_exam_case_result(
  uuid, text, bigint, uuid, uuid, boolean, integer, integer, integer
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.persist_eval_exam_case_result(
  uuid, text, bigint, uuid, uuid, boolean, integer, integer, integer
) TO app_api;

REVOKE ALL ON FUNCTION app.finalize_eval_exam(
  uuid, text, bigint, uuid, boolean, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.finalize_eval_exam(
  uuid, text, bigint, uuid, boolean, text
) TO app_api;

REVOKE ALL ON FUNCTION app.cancel_eval_exam(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.cancel_eval_exam(uuid, text, bigint, uuid)
  TO app_api;

REVOKE ALL ON FUNCTION app.get_eval_exam_run(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_eval_exam_run(uuid, text, bigint, uuid)
  TO app_api;

REVOKE ALL ON FUNCTION app.get_latest_eval_exam_report(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_latest_eval_exam_report(uuid, text, bigint)
  TO app_api;

REVOKE ALL ON FUNCTION app.purge_expired_eval_exam_runs(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.purge_expired_eval_exam_runs(uuid, text, bigint)
  TO app_api;

COMMENT ON FUNCTION app.enqueue_eval_exam(
  uuid, text, bigint, text, text, text, text, text
) IS
  'Owner/admin exam enqueue. Creates a hidden evaluation conversation. Holdout rejected.';

COMMENT ON FUNCTION app.get_latest_eval_exam_report(uuid, text, bigint) IS
  'Latest succeeded count-only report. Ignores partial/failed/cancelled runs.';
