-- Local PDF evaluation workspace: bounded authorized representative passages
-- for the current document version. SECURITY INVOKER, app_api only.

CREATE FUNCTION app.list_authorized_eval_passages(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_version_id uuid,
  p_limit integer,
  p_after_chunk_id uuid
)
RETURNS TABLE (
  chunk_id uuid,
  document_id uuid,
  version_id uuid,
  page_number integer,
  section_path text[],
  raw_text text,
  is_search_representative boolean
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
DECLARE
  bounded_limit integer;
BEGIN
  IF p_version_id IS NULL THEN
    RETURN;
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  bounded_limit := LEAST(GREATEST(COALESCE(p_limit, 40), 1), 60);

  PERFORM set_config('statement_timeout', '8000', true);

  RETURN QUERY
  SELECT
    c.id,
    c.document_id,
    c.version_id,
    c.page_number,
    c.section_path,
    c.raw_text,
    c.is_search_representative
  FROM app.document_chunks AS c
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND c.version_id = p_version_id
    AND c.is_search_representative IS TRUE
    AND dv.status IN (
      'hybrid_ready'::app.document_status,
      'graph_pending'::app.document_status,
      'graph_ready'::app.document_status,
      'graph_ineligible'::app.document_status
    )
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
    AND (
      p_after_chunk_id IS NULL
      OR c.chunk_index > (
        SELECT inner_c.chunk_index
        FROM app.document_chunks AS inner_c
        WHERE inner_c.id = p_after_chunk_id
          AND inner_c.version_id = p_version_id
          AND inner_c.deleted_at IS NULL
      )
    )
  ORDER BY c.chunk_index ASC, c.id ASC
  LIMIT bounded_limit;
END;
$fn$;

COMMENT ON FUNCTION app.list_authorized_eval_passages(
  uuid, text, bigint, uuid, integer, uuid
) IS
  'ACL/current-version representative passages for the local PDF eval workspace. Bound 60.';

REVOKE ALL ON FUNCTION app.list_authorized_eval_passages(
  uuid, text, bigint, uuid, integer, uuid
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.list_authorized_eval_passages(
  uuid, text, bigint, uuid, integer, uuid
) TO app_api;
