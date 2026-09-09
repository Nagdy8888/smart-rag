-- Additive security-invoker heading inventory for one authorized current version.
-- Returns section paths and page ranges only. No raw_text.

CREATE OR REPLACE FUNCTION app.retrieve_heading_inventory(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_version_id uuid
)
RETURNS TABLE (
  section_path text[],
  page_start integer,
  page_end integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
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

  RETURN QUERY
  SELECT
    c.section_path,
    MIN(c.page_number)::integer,
    MAX(c.page_number)::integer
  FROM app.document_chunks AS c
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE c.version_id = p_version_id
    AND c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND dv.status IN (
      'hybrid_ready'::app.document_status,
      'graph_pending'::app.document_status,
      'graph_ready'::app.document_status,
      'graph_ineligible'::app.document_status
    )
    AND cardinality(c.section_path) > 0
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  GROUP BY c.section_path
  ORDER BY MIN(c.chunk_index), MIN(c.id);
END;
$fn$;

COMMENT ON FUNCTION app.retrieve_heading_inventory(uuid, text, bigint, uuid) IS
  'Security-invoker major headings for one current authorized version. No raw text.';

REVOKE ALL ON FUNCTION app.retrieve_heading_inventory(uuid, text, bigint, uuid)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.retrieve_heading_inventory(uuid, text, bigint, uuid)
  TO app_api;
