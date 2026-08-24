-- P08-09: durable query-run user/assistant messages and runtime resume.
-- Expand-only. Existing applied migrations stay immutable.

ALTER TABLE app.messages
  ADD COLUMN IF NOT EXISTS run_id uuid REFERENCES app.runs (id) ON DELETE SET NULL;

COMMENT ON COLUMN app.messages.run_id IS
  'Owning query run when the row is the admitted user input or verified assistant answer.';

CREATE UNIQUE INDEX IF NOT EXISTS messages_one_user_per_run_uq
  ON app.messages (run_id)
  WHERE run_id IS NOT NULL AND role = 'user';

CREATE UNIQUE INDEX IF NOT EXISTS messages_one_assistant_per_run_uq
  ON app.messages (run_id)
  WHERE run_id IS NOT NULL AND role = 'assistant';

CREATE INDEX IF NOT EXISTS messages_run_id_idx
  ON app.messages (run_id)
  WHERE run_id IS NOT NULL;

CREATE OR REPLACE FUNCTION app.append_query_message(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_run_id uuid,
  p_role text,
  p_content text
)
RETURNS TABLE (message_id uuid)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
  run_row app.runs%ROWTYPE;
  existing_id uuid;
  inserted_id uuid;
  bounded text;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_message:authorization_rejected';
  END IF;

  IF p_role IS NULL OR p_role NOT IN ('user', 'assistant') THEN
    RAISE EXCEPTION 'query_message:invalid_role';
  END IF;

  IF p_content IS NULL OR btrim(p_content) = '' THEN
    RAISE EXCEPTION 'query_message:empty_content';
  END IF;

  bounded := left(p_content, 16384);

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_message:conversation_not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_message:conversation_deleted';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_message:conversation_forbidden';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_message:run_forbidden';
  END IF;

  IF run_row.conversation_id IS DISTINCT FROM p_conversation_id THEN
    RAISE EXCEPTION 'query_message:run_conversation_mismatch';
  END IF;

  SELECT m.id INTO existing_id
  FROM app.messages AS m
  WHERE m.run_id = p_run_id
    AND m.role = p_role
  LIMIT 1;

  IF existing_id IS NOT NULL THEN
    message_id := existing_id;
    RETURN NEXT;
    RETURN;
  END IF;

  INSERT INTO app.messages (conversation_id, role, content, run_id)
  VALUES (p_conversation_id, p_role, bounded, p_run_id)
  RETURNING app.messages.id INTO inserted_id;

  message_id := inserted_id;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.append_query_message(
  uuid, text, bigint, uuid, uuid, text, text
) IS
  'Creator-only idempotent insert of one user or assistant message bound to a query run.';

REVOKE ALL ON FUNCTION app.append_query_message(
  uuid, text, bigint, uuid, uuid, text, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.append_query_message(
  uuid, text, bigint, uuid, uuid, text, text
) TO app_api;

CREATE OR REPLACE FUNCTION app.load_query_run_user_message(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (content text)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_message:authorization_rejected';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_message:run_forbidden';
  END IF;

  RETURN QUERY
  SELECT m.content
  FROM app.messages AS m
  WHERE m.run_id = p_run_id
    AND m.role = 'user'
  LIMIT 1;
END;
$fn$;

COMMENT ON FUNCTION app.load_query_run_user_message(uuid, text, bigint, uuid) IS
  'Creator-only load of the admitted user message for one query run.';

REVOKE ALL ON FUNCTION app.load_query_run_user_message(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.load_query_run_user_message(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.load_query_run_runtime(
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
  user_message text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  reservation_row app.budget_reservations%ROWTYPE;
  conversation_row app.conversations%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = run_row.conversation_id;

  IF NOT FOUND OR conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  IF run_row.reservation_id IS NOT NULL THEN
    SELECT * INTO reservation_row
    FROM app.budget_reservations AS br
    WHERE br.id = run_row.reservation_id;
  END IF;

  run_id := run_row.id;
  conversation_id := run_row.conversation_id;
  reservation_id := run_row.reservation_id;
  status := run_row.status;
  route_family := run_row.route_family;
  deadline_at := run_row.deadline_at;
  recursion_limit := run_row.recursion_limit;
  correction_ceiling := run_row.correction_ceiling;
  subquestion_ceiling := run_row.subquestion_ceiling;
  model_call_ceiling := run_row.model_call_ceiling;
  tool_ceiling := run_row.tool_ceiling;
  discovery_ceiling := run_row.discovery_ceiling;
  manifest_ceiling := run_row.manifest_ceiling;
  side_effect_ceiling := run_row.side_effect_ceiling;
  reserved_amount_usd := COALESCE(reservation_row.amount_usd, 0);
  remaining_usd := COALESCE(reservation_row.remaining_usd, reservation_row.amount_usd, 0);
  remaining_prompt_tokens := COALESCE(reservation_row.remaining_prompt_tokens, 0);
  remaining_completion_tokens := COALESCE(
    reservation_row.remaining_completion_tokens,
    0
  );
  optimistic_version := COALESCE(reservation_row.optimistic_version, 1);
  heartbeat_at := run_row.heartbeat_at;
  request_payload_hash := run_row.request_payload_hash;

  SELECT m.content
  INTO user_message
  FROM app.messages AS m
  WHERE m.run_id = p_run_id
    AND m.role = 'user'
  LIMIT 1;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.load_query_run_runtime(uuid, text, bigint, uuid) IS
  'Creator-only rebuild of admit-shaped runtime plus durable user text for resume.';

REVOKE ALL ON FUNCTION app.load_query_run_runtime(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.load_query_run_runtime(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.fail_query_run(
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
  created_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  IF run_row.status = 'failed'::app.run_status THEN
    id := run_row.id;
    conversation_id := run_row.conversation_id;
    creator_user_id := run_row.creator_user_id;
    status := run_row.status;
    reservation_id := run_row.reservation_id;
    created_at := run_row.created_at;
    IF reservation_id IS NOT NULL THEN
      PERFORM app.true_up_query_reservation_internal(reservation_id);
    END IF;
    RETURN NEXT;
    RETURN;
  END IF;

  IF run_row.status NOT IN (
      'pending'::app.run_status,
      'running'::app.run_status
    ) THEN
    RAISE EXCEPTION 'query_admission:run_not_failable';
  END IF;

  UPDATE app.runs
  SET
    status = 'failed'::app.run_status,
    completed_at = timezone('utc', now())
  WHERE app.runs.id = p_run_id
    AND app.runs.status IN (
      'pending'::app.run_status,
      'running'::app.run_status
    )
  RETURNING
    app.runs.id,
    app.runs.conversation_id,
    app.runs.creator_user_id,
    app.runs.status,
    app.runs.reservation_id,
    app.runs.created_at
  INTO id, conversation_id, creator_user_id, status, reservation_id, created_at;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:run_not_failable';
  END IF;

  IF reservation_id IS NOT NULL THEN
    PERFORM app.true_up_query_reservation_internal(reservation_id);
  END IF;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.fail_query_run(uuid, text, bigint, uuid) IS
  'Creator-only fail for pending/running query runs. True-ups the reservation once.';

REVOKE ALL ON FUNCTION app.fail_query_run(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.fail_query_run(uuid, text, bigint, uuid)
  TO app_api;
