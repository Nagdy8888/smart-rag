-- Additive requested search scope on query runs.
-- Expand-only: new column with default, versioned RPCs wrapping existing
-- admit/runtime/get functions. Old signatures stay callable.

ALTER TABLE app.runs
  ADD COLUMN requested_search_scope text NOT NULL DEFAULT 'auto';

ALTER TABLE app.runs
  ADD CONSTRAINT runs_requested_search_scope_chk
  CHECK (
    requested_search_scope IN (
      'auto',
      'company_documents',
      'general_knowledge'
    )
  );

COMMENT ON COLUMN app.runs.requested_search_scope IS
  'Client source preference fixed at admission. Not authorization.';

CREATE OR REPLACE FUNCTION app.admit_query_run_v2(
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
      'general_knowledge'
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

COMMENT ON FUNCTION app.admit_query_run_v2(
  uuid, text, bigint, uuid, text, text, text, text, text, timestamptz
) IS
  'Creator-only admit wrapper that persists requested search scope. Calls existing admit_query_run once.';

REVOKE ALL ON FUNCTION app.admit_query_run_v2(
  uuid, text, bigint, uuid, text, text, text, text, text, timestamptz
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.admit_query_run_v2(
  uuid, text, bigint, uuid, text, text, text, text, text, timestamptz
) TO app_api;

CREATE OR REPLACE FUNCTION app.load_query_run_runtime_v2(
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
DECLARE
  loaded RECORD;
  stored_scope text;
BEGIN
  SELECT *
  INTO loaded
  FROM app.load_query_run_runtime(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );

  IF NOT FOUND THEN
    RETURN;
  END IF;

  SELECT COALESCE(r.requested_search_scope, 'auto')
  INTO stored_scope
  FROM app.runs AS r
  WHERE r.id = loaded.run_id;

  run_id := loaded.run_id;
  conversation_id := loaded.conversation_id;
  reservation_id := loaded.reservation_id;
  status := loaded.status;
  route_family := loaded.route_family;
  deadline_at := loaded.deadline_at;
  recursion_limit := loaded.recursion_limit;
  correction_ceiling := loaded.correction_ceiling;
  subquestion_ceiling := loaded.subquestion_ceiling;
  model_call_ceiling := loaded.model_call_ceiling;
  tool_ceiling := loaded.tool_ceiling;
  discovery_ceiling := loaded.discovery_ceiling;
  manifest_ceiling := loaded.manifest_ceiling;
  side_effect_ceiling := loaded.side_effect_ceiling;
  reserved_amount_usd := loaded.reserved_amount_usd;
  remaining_usd := loaded.remaining_usd;
  remaining_prompt_tokens := loaded.remaining_prompt_tokens;
  remaining_completion_tokens := loaded.remaining_completion_tokens;
  optimistic_version := loaded.optimistic_version;
  heartbeat_at := loaded.heartbeat_at;
  request_payload_hash := loaded.request_payload_hash;
  user_message := loaded.user_message;
  requested_search_scope := COALESCE(stored_scope, 'auto');
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.load_query_run_runtime_v2(uuid, text, bigint, uuid) IS
  'Creator-only runtime loader plus persisted requested search scope for resume.';

REVOKE ALL ON FUNCTION app.load_query_run_runtime_v2(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.load_query_run_runtime_v2(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.get_query_run_v2(
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
DECLARE
  loaded RECORD;
  stored_scope text;
BEGIN
  SELECT *
  INTO loaded
  FROM app.get_query_run(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );

  IF NOT FOUND THEN
    RETURN;
  END IF;

  SELECT COALESCE(r.requested_search_scope, 'auto')
  INTO stored_scope
  FROM app.runs AS r
  WHERE r.id = loaded.id;

  id := loaded.id;
  conversation_id := loaded.conversation_id;
  creator_user_id := loaded.creator_user_id;
  status := loaded.status;
  reservation_id := loaded.reservation_id;
  created_at := loaded.created_at;
  requested_search_scope := COALESCE(stored_scope, 'auto');
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.get_query_run_v2(uuid, text, bigint, uuid) IS
  'Creator-only run fetch plus requested search scope for Run Details.';

REVOKE ALL ON FUNCTION app.get_query_run_v2(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_query_run_v2(uuid, text, bigint, uuid)
  TO app_api;
