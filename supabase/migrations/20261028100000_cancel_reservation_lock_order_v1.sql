-- Forward repair for the recorded cancellation/citation deadlock.
-- No grants, budgets, accounting rows or runtime envelopes are expanded.
CREATE OR REPLACE FUNCTION app.cancel_query_run(
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

  -- Model consume holds the reservation until its node commits, then citation
  -- insertion locks the run. Cancel must take those locks in that same order.
  -- Authenticate ownership above before taking any reservation lock.
  IF run_row.reservation_id IS NOT NULL THEN
    PERFORM 1 FROM app.budget_reservations br
    WHERE br.id = run_row.reservation_id FOR UPDATE;
  END IF;
  SELECT * INTO run_row FROM app.runs r WHERE r.id = p_run_id FOR UPDATE;
  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  IF run_row.status = 'cancelled'::app.run_status THEN
    id := run_row.id;
    conversation_id := run_row.conversation_id;
    creator_user_id := run_row.creator_user_id;
    status := run_row.status;
    reservation_id := run_row.reservation_id;
    created_at := run_row.created_at;
    RETURN NEXT;
    RETURN;
  END IF;

  IF run_row.status NOT IN (
      'pending'::app.run_status,
      'running'::app.run_status
    ) THEN
    RAISE EXCEPTION 'query_admission:run_not_cancellable';
  END IF;

  UPDATE app.runs
  SET
    status = 'cancelled'::app.run_status,
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
    RAISE EXCEPTION 'query_admission:run_not_cancellable';
  END IF;

  IF reservation_id IS NOT NULL THEN
    PERFORM app.true_up_query_reservation_internal(reservation_id);
  END IF;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.cancel_query_run(uuid, text, bigint, uuid) IS
  'Creator-only cancel for pending/running query runs. True-ups the reservation. Not SSE transport.';

REVOKE ALL ON FUNCTION app.cancel_query_run(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.cancel_query_run(uuid, text, bigint, uuid)
  TO app_api;
