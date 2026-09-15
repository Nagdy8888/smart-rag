-- Additive Web admission: widen requested_search_scope and route_family
-- CHECKs, add the web_research envelope, and admit/load/get v3 wrapping v2.
-- Expand-only. v2 signatures stay callable.

ALTER TABLE app.runs
  DROP CONSTRAINT IF EXISTS runs_requested_search_scope_chk;
ALTER TABLE app.runs
  ADD CONSTRAINT runs_requested_search_scope_chk
    CHECK (
      requested_search_scope IN (
        'auto',
        'company_documents',
        'general_knowledge',
        'web'
      )
    );

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
        'scoped_refusal',
        'web_research'
      )
    );

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
    WHEN 'web_research' THEN
      deadline_seconds := 50;
      model_call_ceiling := 5;
      tool_ceiling := 5;
      envelope_usd := 2.00;
      envelope_prompt_tokens := 40000;
      envelope_completion_tokens := 10000;
    ELSE
      RAISE EXCEPTION 'query_admission:unknown_route_family';
  END CASE;

  recursion_limit := 24;
  IF p_route_family = 'web_research' THEN
    correction_ceiling := 0;
  ELSE
    correction_ceiling := 1;
  END IF;
  subquestion_ceiling := 3;
  discovery_ceiling := 1;
  manifest_ceiling := 3;
  side_effect_ceiling := 1;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.query_route_envelope(text) IS
  'Server-owned Phase 6 route envelopes including web_research. Not client authority.';

CREATE OR REPLACE FUNCTION app.admit_query_run_v3(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_idempotency_key text,
  p_payload_hash text,
  p_route_family text,
  p_requested_search_scope text,
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
  request_payload_hash text,
  requested_search_scope text
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  admitted RECORD;
  stored_scope text;
BEGIN
  IF p_requested_search_scope IS NULL
    OR p_requested_search_scope NOT IN (
      'auto',
      'company_documents',
      'general_knowledge',
      'web'
    ) THEN
    RAISE EXCEPTION 'query_admission:invalid_search_scope';
  END IF;

  SELECT *
  INTO admitted
  FROM app.admit_query_run(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_conversation_id,
    p_idempotency_key,
    p_payload_hash,
    p_route_family,
    p_session_id,
    p_token_issued_at
  );

  IF NOT FOUND THEN
    RETURN;
  END IF;

  IF admitted.reconnect IS NOT TRUE THEN
    UPDATE app.runs AS r
    SET requested_search_scope = p_requested_search_scope
    WHERE r.id = admitted.run_id;
    stored_scope := p_requested_search_scope;
  ELSE
    SELECT r.requested_search_scope
    INTO stored_scope
    FROM app.runs AS r
    WHERE r.id = admitted.run_id;
    IF stored_scope IS DISTINCT FROM p_requested_search_scope THEN
      RAISE EXCEPTION 'query_admission:key_collision';
    END IF;
  END IF;

  run_id := admitted.run_id;
  reservation_id := admitted.reservation_id;
  reconnect := admitted.reconnect;
  status := admitted.status;
  route_family := admitted.route_family;
  deadline_at := admitted.deadline_at;
  recursion_limit := admitted.recursion_limit;
  correction_ceiling := admitted.correction_ceiling;
  subquestion_ceiling := admitted.subquestion_ceiling;
  model_call_ceiling := admitted.model_call_ceiling;
  tool_ceiling := admitted.tool_ceiling;
  discovery_ceiling := admitted.discovery_ceiling;
  manifest_ceiling := admitted.manifest_ceiling;
  side_effect_ceiling := admitted.side_effect_ceiling;
  reserved_amount_usd := admitted.reserved_amount_usd;
  remaining_usd := admitted.remaining_usd;
  remaining_prompt_tokens := admitted.remaining_prompt_tokens;
  remaining_completion_tokens := admitted.remaining_completion_tokens;
  optimistic_version := admitted.optimistic_version;
  heartbeat_at := admitted.heartbeat_at;
  request_payload_hash := admitted.request_payload_hash;
  requested_search_scope := stored_scope;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.admit_query_run_v3(
  uuid, text, bigint, uuid, text, text, text, text, text, timestamptz
) IS
  'Creator-only admit wrapper that persists auto/company/general/web scope. Calls admit_query_run once. v2 stays callable.';

REVOKE ALL ON FUNCTION app.admit_query_run_v3(
  uuid, text, bigint, uuid, text, text, text, text, text, timestamptz
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.admit_query_run_v3(
  uuid, text, bigint, uuid, text, text, text, text, text, timestamptz
) TO app_api;

CREATE OR REPLACE FUNCTION app.load_query_run_runtime_v3(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  run_id uuid,
  conversation_id uuid,
  reservation_id uuid,
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
  request_payload_hash text,
  user_message text,
  requested_search_scope text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RETURN QUERY
  SELECT *
  FROM app.load_query_run_runtime_v2(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );
END;
$fn$;

COMMENT ON FUNCTION app.load_query_run_runtime_v3(uuid, text, bigint, uuid) IS
  'Creator-only runtime loader plus persisted requested search scope including web.';

REVOKE ALL ON FUNCTION app.load_query_run_runtime_v3(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.load_query_run_runtime_v3(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.get_query_run_v3(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  id uuid,
  conversation_id uuid,
  creator_user_id uuid,
  status app.run_status,
  reservation_id uuid,
  created_at timestamptz,
  requested_search_scope text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RETURN QUERY
  SELECT *
  FROM app.get_query_run_v2(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );
END;
$fn$;

COMMENT ON FUNCTION app.get_query_run_v3(uuid, text, bigint, uuid) IS
  'Creator-only run fetch plus requested search scope including web.';

REVOKE ALL ON FUNCTION app.get_query_run_v3(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_query_run_v3(uuid, text, bigint, uuid)
  TO app_api;
