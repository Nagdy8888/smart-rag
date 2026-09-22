-- Reject a second upload of bytes that already belong to a visible document.
-- Returns the oldest readable, non-deleted document for one content hash.

CREATE OR REPLACE FUNCTION app.find_visible_document_by_content_hash(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_content_hash text
)
RETURNS uuid
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

  RETURN (
    SELECT d.id
    FROM app.document_versions AS dv
    JOIN app.documents AS d ON d.id = dv.document_id
    WHERE lower(dv.content_hash) = lower(p_content_hash)
      AND d.deleted_at IS NULL
      AND dv.deleted_at IS NULL
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
    ORDER BY d.created_at ASC
    LIMIT 1
  );
END;
$fn$;

COMMENT ON FUNCTION app.find_visible_document_by_content_hash(
  uuid, text, bigint, text
) IS
  'Oldest ACL-visible non-deleted document whose version content_hash matches. NULL when none.';

REVOKE ALL ON FUNCTION app.find_visible_document_by_content_hash(
  uuid, text, bigint, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.find_visible_document_by_content_hash(
  uuid, text, bigint, text
) TO app_api;
