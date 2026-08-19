-- PRD-M-022: Keyset pagination for document and conversation lists.
-- Default page 50, hard max 200. Original three-argument RPCs stay and are
-- bounded to 50 rows so leftover fetchall callers cannot serialize the tenant.

CREATE OR REPLACE FUNCTION app.list_visible_documents(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  id uuid,
  title text,
  visibility app.document_visibility,
  current_version_id uuid,
  visibility_generation bigint
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT
    d.id,
    d.title,
    d.visibility,
    d.current_version_id,
    d.visibility_generation
  FROM app.documents AS d
  WHERE app.validate_caller_context(
      caller_user_id,
      caller_role,
      caller_authorization_version
    )
    AND d.deleted_at IS NULL
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ORDER BY d.created_at DESC, d.id DESC
  LIMIT 50;
$$;

COMMENT ON FUNCTION app.list_visible_documents(uuid, text, bigint) IS
  'Security-invoker document listing. Bounded to 50 rows; use list_visible_documents_page for cursors.';

GRANT EXECUTE ON FUNCTION app.list_visible_documents(uuid, text, bigint) TO app_api;

CREATE OR REPLACE FUNCTION app.list_user_conversations(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  id uuid,
  creator_user_id uuid,
  title text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT c.id, c.creator_user_id, c.title
  FROM app.conversations AS c
  WHERE app.validate_caller_context(
      caller_user_id,
      caller_role,
      caller_authorization_version
    )
    AND c.deleted_at IS NULL
    AND (
      c.creator_user_id = caller_user_id
      OR caller_role IN ('owner', 'admin')
    )
  ORDER BY c.created_at DESC, c.id DESC
  LIMIT 50;
$$;

COMMENT ON FUNCTION app.list_user_conversations(uuid, text, bigint) IS
  'Creator-private conversations with owner/admin audit visibility. Bounded to 50 rows.';

GRANT EXECUTE ON FUNCTION app.list_user_conversations(uuid, text, bigint) TO app_api;

CREATE OR REPLACE FUNCTION app.list_visible_documents_page(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_limit integer DEFAULT 50,
  p_cursor_created_at timestamptz DEFAULT NULL,
  p_cursor_id uuid DEFAULT NULL
)
RETURNS TABLE (
  id uuid,
  title text,
  visibility app.document_visibility,
  current_version_id uuid,
  visibility_generation bigint,
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
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;

  IF (p_cursor_created_at IS NULL) <> (p_cursor_id IS NULL) THEN
    RAISE EXCEPTION 'documents:invalid_cursor';
  END IF;

  capped_limit := GREATEST(1, LEAST(COALESCE(p_limit, 50), 200));

  RETURN QUERY
  SELECT
    d.id,
    d.title,
    d.visibility,
    d.current_version_id,
    d.visibility_generation,
    d.created_at
  FROM app.documents AS d
  WHERE d.deleted_at IS NULL
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
    AND (
      p_cursor_created_at IS NULL
      OR (d.created_at, d.id) < (p_cursor_created_at, p_cursor_id)
    )
  ORDER BY d.created_at DESC, d.id DESC
  LIMIT capped_limit;
END;
$fn$;

COMMENT ON FUNCTION app.list_visible_documents_page(uuid, text, bigint, integer, timestamptz, uuid) IS
  'Keyset document listing. Default 50, max 200, cursor is (created_at, id).';

REVOKE ALL ON FUNCTION app.list_visible_documents_page(
  uuid, text, bigint, integer, timestamptz, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_visible_documents_page(
  uuid, text, bigint, integer, timestamptz, uuid
) TO app_api;

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

COMMENT ON FUNCTION app.list_user_conversations_page(uuid, text, bigint, integer, timestamptz, uuid) IS
  'Keyset conversation listing. Default 50, max 200, cursor is (created_at, id).';

REVOKE ALL ON FUNCTION app.list_user_conversations_page(
  uuid, text, bigint, integer, timestamptz, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_user_conversations_page(
  uuid, text, bigint, integer, timestamptz, uuid
) TO app_api;
