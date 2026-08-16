-- Phase 6 Packet 2: bounded creator-only conversation memory load for query
-- preparation. Expand-only. No DROP TABLE / DROP COLUMN. Packet 7 owns
-- LangGraph store summaries; this RPC loads last N messages only.

CREATE OR REPLACE FUNCTION app.load_query_memory(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_limit integer DEFAULT 12
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

  IF p_limit IS NULL OR p_limit < 1 OR p_limit > 12 THEN
    RAISE EXCEPTION 'query_memory:invalid_limit';
  END IF;

  bounded_limit := p_limit;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_deleted';
  END IF;

  -- Creator-only, matching admit_query_run. Owner/admin audit SELECT on
  -- conversations does not authorize query-memory load on another thread.
  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_memory:conversation_forbidden';
  END IF;

  RETURN QUERY
  SELECT
    m.id,
    m.role,
    left(m.content, 1500),
    m.created_at
  FROM app.messages AS m
  WHERE m.conversation_id = p_conversation_id
  ORDER BY m.created_at DESC, m.id DESC
  LIMIT bounded_limit;
END;
$fn$;

COMMENT ON FUNCTION app.load_query_memory(uuid, text, bigint, uuid, integer) IS
  'Loads at most 12 recent messages for the conversation creator. Untrusted data. Never joins source documents. No summary store (packet 7).';

REVOKE ALL ON FUNCTION app.load_query_memory(
  uuid, text, bigint, uuid, integer
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.load_query_memory(
  uuid, text, bigint, uuid, integer
) TO app_api;
