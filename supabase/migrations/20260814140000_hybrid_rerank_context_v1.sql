-- Phase 4 Packet 5: authorized chunk context for rerank excerpts and
-- parent/adjacent expansion. Parents may be non-representative.
-- Do not install pg_search on managed Supabase.

CREATE OR REPLACE FUNCTION app.fetch_authorized_chunk_context(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_chunk_ids uuid[]
)
RETURNS TABLE (
  chunk_id uuid,
  document_id uuid,
  version_id uuid,
  parent_chunk_id uuid,
  chunk_index integer,
  page_number integer,
  section_path text[],
  token_count integer,
  raw_text text,
  is_search_representative boolean
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
BEGIN
  IF p_chunk_ids IS NULL OR cardinality(p_chunk_ids) = 0 THEN
    RETURN;
  END IF;

  IF cardinality(p_chunk_ids) > 75 THEN
    RAISE EXCEPTION 'context_batch_exceeds_limit';
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  PERFORM set_config('statement_timeout', '8000', true);

  RETURN QUERY
  WITH requested AS (
    SELECT
      requested_id.chunk_id,
      requested_id.ordinality
    FROM unnest(p_chunk_ids) WITH ORDINALITY AS requested_id(chunk_id, ordinality)
  )
  SELECT
    c.id,
    c.document_id,
    c.version_id,
    c.parent_chunk_id,
    c.chunk_index,
    c.page_number,
    c.section_path,
    c.token_count,
    c.raw_text,
    c.is_search_representative
  FROM requested AS req
  INNER JOIN app.document_chunks AS c ON c.id = req.chunk_id
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND dv.status IN (
      'hybrid_ready'::app.document_status,
      'graph_pending'::app.document_status,
      'graph_ready'::app.document_status,
      'graph_ineligible'::app.document_status
    )
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ORDER BY req.ordinality ASC
  LIMIT 75;
END;
$fn$;

COMMENT ON FUNCTION app.fetch_authorized_chunk_context(uuid, text, bigint, uuid[]) IS
  'ACL/current-version chunk context including parent rows. Citations use raw_text.';

REVOKE ALL ON FUNCTION app.fetch_authorized_chunk_context(
  uuid, text, bigint, uuid[]
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.fetch_authorized_chunk_context(
  uuid, text, bigint, uuid[]
) TO app_api;
