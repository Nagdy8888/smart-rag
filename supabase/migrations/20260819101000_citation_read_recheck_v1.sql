-- PRD-M-013: Historical citation GET rechecks ACL and current_version.
-- Unauthorized or non-current chunks are source_unavailable and omit chunk_id.

DROP FUNCTION IF EXISTS app.list_run_citations(uuid, text, bigint, uuid);

CREATE OR REPLACE FUNCTION app.list_run_citations(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  citation_id uuid,
  citation_index integer,
  chunk_id uuid,
  provenance jsonb,
  source_unavailable boolean
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
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.runs AS r
    INNER JOIN app.conversations AS c ON c.id = r.conversation_id
    WHERE r.id = p_run_id
      AND r.creator_user_id = caller_user_id
      AND c.deleted_at IS NULL
  ) THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  RETURN QUERY
  SELECT
    cited.id,
    cited.citation_index,
    CASE
      WHEN cited.chunk_id IS NOT NULL AND NOT cited.recheck_ok THEN NULL
      ELSE cited.chunk_id
    END,
    cited.provenance,
    (
      cited.source_unavailable
      OR (cited.chunk_id IS NOT NULL AND NOT cited.recheck_ok)
    ) AS source_unavailable
  FROM (
    SELECT
      ct.id,
      ct.citation_index,
      ct.chunk_id,
      ct.provenance,
      ct.source_unavailable,
      (
        ct.chunk_id IS NULL
        OR EXISTS (
          SELECT 1
          FROM app.document_chunks AS dc
          INNER JOIN app.documents AS d ON d.id = dc.document_id
          INNER JOIN app.document_versions AS dv ON dv.id = dc.version_id
          WHERE dc.id = ct.chunk_id
            AND dc.deleted_at IS NULL
            AND d.deleted_at IS NULL
            AND dv.deleted_at IS NULL
            AND d.current_version_id IS NOT DISTINCT FROM dc.version_id
            AND app.caller_can_read_document(
              caller_user_id,
              caller_role,
              d.id
            )
        )
      ) AS recheck_ok
    FROM app.citations AS ct
    WHERE ct.run_id = p_run_id
  ) AS cited
  ORDER BY cited.citation_index
  LIMIT 50;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid) IS
  'Creator-only citation identifiers. ACL, deletion, and current-version recheck mark sources unavailable without returning chunk_id.';

REVOKE ALL ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid)
  TO app_api;
