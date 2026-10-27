-- Preserve the existing ownership/ACL boundary; show the cited span, not a page prefix.
CREATE OR REPLACE FUNCTION app.get_run_citation_detail_v1(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_citation_id uuid
)
RETURNS TABLE (
  citation_id uuid,
  citation_index integer,
  chunk_id uuid,
  provenance jsonb,
  source_unavailable boolean,
  source_kind text,
  web_source_id uuid,
  paragraph_index integer,
  document_title text,
  pdf_page_number integer,
  evidence_excerpt text,
  source_url text,
  document_id uuid,
  version_id uuid,
  document_visibility text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  matched integer;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF p_run_id IS NULL OR p_citation_id IS NULL THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  RETURN QUERY
  SELECT
    listed.citation_id,
    listed.citation_index,
    listed.chunk_id,
    listed.provenance,
    CASE
      WHEN listed.source_kind = 'web'
        AND (
          web.src_url IS NULL
          OR web.src_url !~* '^https://'
          OR position('#' IN web.src_url) > 0
          OR web.src_url ~* '://[^/]*@'
          OR web.cited_span IS NULL
          OR btrim(web.cited_span) = ''
          OR position(web.cited_span IN web.src_excerpt) = 0
        )
      THEN TRUE
      ELSE listed.source_unavailable
    END,
    listed.source_kind,
    listed.web_source_id,
    listed.paragraph_index,
    listed.document_title,
    listed.pdf_page_number,
    CASE
      WHEN listed.source_kind = 'web'
        AND web.src_url ~* '^https://'
        AND position('#' IN web.src_url) = 0
        AND web.src_url !~* '://[^/]*@'
        AND web.src_excerpt IS NOT NULL
        AND btrim(web.src_excerpt) <> ''
        AND web.cited_span IS NOT NULL
        AND position(web.cited_span IN web.src_excerpt) > 0
      THEN web.cited_span
      WHEN listed.source_kind = 'company_document' THEN listed.evidence_excerpt
      ELSE NULL
    END,
    CASE
      WHEN listed.source_kind = 'web'
        AND web.src_url ~* '^https://'
        AND position('#' IN web.src_url) = 0
        AND web.src_url !~* '://[^/]*@'
      THEN web.src_url
      ELSE NULL
    END,
    vis.document_id,
    vis.version_id,
    vis.visibility::text
  FROM app.list_run_citations_v4(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  ) AS listed
  LEFT JOIN LATERAL (
    SELECT ws.url AS src_url, ws.excerpt AS src_excerpt, wc.span AS cited_span
    FROM app.web_sources AS ws
    JOIN app.web_citations AS wc ON wc.web_source_id = ws.id
      AND wc.run_id = p_run_id AND wc.id = listed.citation_id
    WHERE ws.id = listed.web_source_id
      AND ws.run_id = p_run_id
  ) AS web ON listed.source_kind = 'web'
  LEFT JOIN LATERAL (
    SELECT
      dc.document_id,
      dc.version_id,
      d.visibility
    FROM app.document_chunks AS dc
    INNER JOIN app.documents AS d ON d.id = dc.document_id
    WHERE dc.id = listed.chunk_id
  ) AS vis ON listed.source_kind = 'company_document'
  WHERE listed.citation_id = p_citation_id;

  GET DIAGNOSTICS matched = ROW_COUNT;
  IF matched = 0 THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;
END;
$fn$;

COMMENT ON FUNCTION app.get_run_citation_detail_v1(
  uuid, text, bigint, uuid, uuid
) IS
  'One owned citation with ACL-rechecked company excerpt (1..1000) or exact contained HTTPS Web citation span. Foreign IDs raise not_found.';

REVOKE ALL ON FUNCTION app.get_run_citation_detail_v1(
  uuid, text, bigint, uuid, uuid
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.get_run_citation_detail_v1(
  uuid, text, bigint, uuid, uuid
) TO app_api;
