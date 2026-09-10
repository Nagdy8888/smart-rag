-- Expand-only citation GET: overlay authorized page/title/section locators.
-- v1 remains. Passage text and Storage URLs stay omitted.

CREATE OR REPLACE FUNCTION app.list_run_citations_v2(
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
    CASE
      WHEN cited.recheck_ok THEN
        cited.provenance || jsonb_strip_nulls(
          jsonb_build_object(
            'page_number', cited.page_number,
            'section_path', CASE
              WHEN cited.section_path IS NULL
                OR cardinality(cited.section_path) = 0
              THEN NULL
              ELSE to_jsonb(cited.section_path)
            END,
            'document_id', cited.document_id,
            'document_title', cited.document_title
          )
        )
      ELSE
        cited.provenance - ARRAY[
          'page_number',
          'section_path',
          'document_title',
          'document_id',
          'sheet_name',
          'range_ref',
          'source_url'
        ]
    END,
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
      dc.page_number,
      dc.section_path,
      dc.document_id,
      d.title AS document_title,
      (
        ct.chunk_id IS NULL
        OR EXISTS (
          SELECT 1
          FROM app.document_chunks AS vis
          INNER JOIN app.documents AS vis_doc ON vis_doc.id = vis.document_id
          INNER JOIN app.document_versions AS vis_ver ON vis_ver.id = vis.version_id
          WHERE vis.id = ct.chunk_id
            AND vis.deleted_at IS NULL
            AND vis_doc.deleted_at IS NULL
            AND vis_ver.deleted_at IS NULL
            AND vis_doc.current_version_id IS NOT DISTINCT FROM vis.version_id
            AND app.caller_can_read_document(
              caller_user_id,
              caller_role,
              vis_doc.id
            )
        )
      ) AS recheck_ok
    FROM app.citations AS ct
    LEFT JOIN app.document_chunks AS dc
      ON dc.id = ct.chunk_id
     AND dc.deleted_at IS NULL
    LEFT JOIN app.documents AS d
      ON d.id = dc.document_id
     AND d.deleted_at IS NULL
    WHERE ct.run_id = p_run_id
  ) AS cited
  ORDER BY cited.citation_index
  LIMIT 50;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_citations_v2(uuid, text, bigint, uuid) IS
  'Creator-only citation identifiers plus authorized page/title/section locators. ACL, deletion, and current-version recheck mark sources unavailable without returning chunk_id or locator identity. Passage text is omitted.';

REVOKE ALL ON FUNCTION app.list_run_citations_v2(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_run_citations_v2(uuid, text, bigint, uuid)
  TO app_api;
