-- UI/UX overhaul P1: creator-only conversation transcript read.
-- Expand-only. No DROP TABLE / DROP COLUMN. Full message content, no
-- 1500-character truncation. User and assistant roles only.

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

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_deleted';
  END IF;

  -- Creator-only. Owner/admin audit SELECT does not authorize transcript
  -- reads on another creator's thread (same rule as load_query_memory).
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

COMMENT ON FUNCTION app.list_conversation_messages(
  uuid, text, bigint, uuid, integer, uuid
) IS
  'Lists creator-owned user/assistant messages newest-first with keyset pagination. Full content. Untrusted data. Never joins source documents.';

REVOKE ALL ON FUNCTION app.list_conversation_messages(
  uuid, text, bigint, uuid, integer, uuid
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.list_conversation_messages(
  uuid, text, bigint, uuid, integer, uuid
) TO app_api;
