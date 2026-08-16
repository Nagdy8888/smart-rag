-- Phase 6 Packet 6: persist sequenced SSE events for resume. Expand-only.
-- Packet 7 owns 7-day idempotency / 30-day event GC and conversation deletion.
-- Tombstoned conversations.deleted_at still deny resume immediately.

CREATE TABLE app.run_events (
  run_id uuid NOT NULL REFERENCES app.runs (id) ON DELETE CASCADE,
  sequence bigint NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  PRIMARY KEY (run_id, sequence),
  CONSTRAINT run_events_sequence_positive CHECK (sequence >= 1),
  CONSTRAINT run_events_type_allowed CHECK (
    event_type IN (
      'schema',
      'status',
      'heartbeat',
      'route_correction',
      'limitation',
      'deadline',
      'partial',
      'cache',
      'coverage',
      'optional_tool_disclosure',
      'citation_preview',
      'token_delta',
      'usage',
      'completed',
      'cancelled',
      'error'
    )
  )
);

COMMENT ON TABLE app.run_events IS
  'Monotonic SSE frames for one query run. Packet 7 reaps completed events after 30 days.';

CREATE UNIQUE INDEX run_events_one_terminal_uq
  ON app.run_events (run_id)
  WHERE event_type IN ('completed', 'cancelled', 'error', 'partial');

ALTER TABLE app.run_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.run_events FORCE ROW LEVEL SECURITY;

CREATE POLICY run_events_creator_private
  ON app.run_events
  FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM app.runs AS r
      WHERE r.id = run_events.run_id
        AND (
          r.creator_user_id = auth.uid()
          OR EXISTS (
            SELECT 1
            FROM app.profiles AS p
            WHERE p.user_id = auth.uid()
              AND p.disabled_at IS NULL
              AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
          )
        )
    )
  );

REVOKE ALL ON TABLE app.run_events
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
GRANT SELECT ON TABLE app.run_events TO authenticated;

CREATE OR REPLACE FUNCTION app.append_run_event(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_event_type text,
  p_payload jsonb
)
RETURNS TABLE (
  run_id uuid,
  sequence bigint,
  event_type text,
  payload jsonb,
  created_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  conversation_deleted timestamptz;
  next_sequence bigint;
  cleaned jsonb;
  forbidden text;
  existing_terminal app.run_events%ROWTYPE;
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
  WHERE r.id = p_run_id
  FOR UPDATE;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  SELECT c.deleted_at INTO conversation_deleted
  FROM app.conversations AS c
  WHERE c.id = run_row.conversation_id;

  IF NOT FOUND OR conversation_deleted IS NOT NULL THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  cleaned := COALESCE(p_payload, '{}'::jsonb)
    - ARRAY[
      'passage',
      'snippet',
      'html',
      'traceback',
      'exception',
      'stack',
      'stacktrace',
      'source_html',
      'retrieved_text',
      'page_content',
      'content_html',
      'secret',
      'password',
      'api_key',
      'token'
    ];

  SELECT k INTO forbidden
  FROM jsonb_object_keys(cleaned) AS k
  WHERE lower(k) IN (
    'passage',
    'snippet',
    'html',
    'traceback',
    'exception',
    'stack',
    'stacktrace',
    'source_html',
    'retrieved_text',
    'page_content',
    'content_html',
    'secret',
    'password',
    'api_key',
    'token'
  )
  LIMIT 1;

  IF forbidden IS NOT NULL THEN
    RAISE EXCEPTION 'query_admission:payload_forbidden';
  END IF;

  IF p_event_type IN ('completed', 'cancelled', 'error', 'partial') THEN
    SELECT * INTO existing_terminal
    FROM app.run_events AS e
    WHERE e.run_id = p_run_id
      AND e.event_type IN ('completed', 'cancelled', 'error', 'partial')
    ORDER BY e.sequence
    LIMIT 1;

    IF FOUND THEN
      run_id := existing_terminal.run_id;
      sequence := existing_terminal.sequence;
      event_type := existing_terminal.event_type;
      payload := existing_terminal.payload;
      created_at := existing_terminal.created_at;
      RETURN NEXT;
      RETURN;
    END IF;
  END IF;

  SELECT COALESCE(MAX(e.sequence), 0) + 1
  INTO next_sequence
  FROM app.run_events AS e
  WHERE e.run_id = p_run_id;

  INSERT INTO app.run_events (run_id, sequence, event_type, payload)
  VALUES (p_run_id, next_sequence, p_event_type, cleaned)
  RETURNING
    app.run_events.run_id,
    app.run_events.sequence,
    app.run_events.event_type,
    app.run_events.payload,
    app.run_events.created_at
  INTO run_id, sequence, event_type, payload, created_at;

  IF p_event_type = 'completed' THEN
    UPDATE app.runs
    SET
      status = 'completed'::app.run_status,
      completed_at = timezone('utc', now())
    WHERE app.runs.id = p_run_id
      AND app.runs.status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      );
  ELSIF p_event_type = 'cancelled' THEN
    UPDATE app.runs
    SET
      status = 'cancelled'::app.run_status,
      completed_at = timezone('utc', now())
    WHERE app.runs.id = p_run_id
      AND app.runs.status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      );
  ELSIF p_event_type = 'partial' THEN
    UPDATE app.runs
    SET
      status = 'partial'::app.run_status,
      completed_at = timezone('utc', now())
    WHERE app.runs.id = p_run_id
      AND app.runs.status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      );
  ELSIF p_event_type = 'error' THEN
    UPDATE app.runs
    SET
      status = 'failed'::app.run_status,
      completed_at = timezone('utc', now())
    WHERE app.runs.id = p_run_id
      AND app.runs.status IN (
        'pending'::app.run_status,
        'running'::app.run_status
      );
  END IF;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.append_run_event(uuid, text, bigint, uuid, text, jsonb) IS
  'Allocate the next run-local sequence under a run lock after ownership and undeleted conversation checks. app_api only.';

REVOKE ALL ON FUNCTION app.append_run_event(uuid, text, bigint, uuid, text, jsonb)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.append_run_event(uuid, text, bigint, uuid, text, jsonb)
  TO app_api;

CREATE OR REPLACE FUNCTION app.list_run_events_after(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_after bigint
)
RETURNS TABLE (
  run_id uuid,
  sequence bigint,
  event_type text,
  payload jsonb,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  conversation_deleted timestamptz;
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

  SELECT c.deleted_at INTO conversation_deleted
  FROM app.conversations AS c
  WHERE c.id = run_row.conversation_id;

  IF NOT FOUND OR conversation_deleted IS NOT NULL THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  RETURN QUERY
  SELECT e.run_id, e.sequence, e.event_type, e.payload, e.created_at
  FROM app.run_events AS e
  WHERE e.run_id = p_run_id
    AND e.sequence > COALESCE(p_after, 0)
  ORDER BY e.sequence;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_events_after(uuid, text, bigint, uuid, bigint) IS
  'Replay persisted SSE events with sequence > after. Creator-only. Tombstoned conversations deny.';

REVOKE ALL ON FUNCTION app.list_run_events_after(uuid, text, bigint, uuid, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_run_events_after(uuid, text, bigint, uuid, bigint)
  TO app_api;
