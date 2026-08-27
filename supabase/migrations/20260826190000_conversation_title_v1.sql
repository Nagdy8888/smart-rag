-- LLM session titles: creator-only source excerpts and title update.
-- Expand-only. No DROP TABLE / DROP COLUMN.

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

  IF NOT FOUND THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  -- Creator-only. Owner/admin audit read does not authorize title writes
  -- or excerpt export for another creator's thread.
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

COMMENT ON FUNCTION app.get_conversation_title_source(
  uuid, text, bigint, uuid
) IS
  'Creator-only first user/assistant excerpts plus current title for LLM session titles. Untrusted data. Never joins source documents.';

REVOKE ALL ON FUNCTION app.get_conversation_title_source(
  uuid, text, bigint, uuid
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.get_conversation_title_source(
  uuid, text, bigint, uuid
) TO app_api;

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

  IF NOT FOUND THEN
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

COMMENT ON FUNCTION app.update_conversation_title(
  uuid, text, bigint, uuid, text
) IS
  'Creator-only conversation title replace. Title is untrusted data. Missing, deleted, and foreign rows raise not_found.';

REVOKE ALL ON FUNCTION app.update_conversation_title(
  uuid, text, bigint, uuid, text
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.update_conversation_title(
  uuid, text, bigint, uuid, text
) TO app_api;
