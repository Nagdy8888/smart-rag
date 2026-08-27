-- Add created_at to the one-document ACL read so detail Overview can
-- show the same created time the list already returns.

DROP FUNCTION IF EXISTS app.get_visible_document(uuid, text, bigint, uuid);

CREATE FUNCTION app.get_visible_document(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid
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
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;

  RETURN QUERY
  SELECT
    d.id,
    d.title,
    d.visibility,
    d.current_version_id,
    d.visibility_generation,
    d.created_at
  FROM app.documents AS d
  WHERE d.id = p_document_id
    AND d.deleted_at IS NULL
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id);
END;
$fn$;

COMMENT ON FUNCTION app.get_visible_document(uuid, text, bigint, uuid) IS
  'One ACL-visible non-deleted document including created_at. Unauthorized ids return no row.';

REVOKE ALL ON FUNCTION app.get_visible_document(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_visible_document(uuid, text, bigint, uuid)
  TO app_api;
