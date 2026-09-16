-- P06-53: additive transcript-v3 run metadata and one-citation detail RPC.
-- Expand-only. v1 ``list_conversation_messages`` and v2 stay callable.

CREATE OR REPLACE FUNCTION app.list_conversation_messages_v3(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_limit integer DEFAULT 50,
  p_before_id uuid DEFAULT NULL
)
RETURNS TABLE (
  message_id uuid,
  role text,
  content text,
  created_at timestamptz,
  run_id uuid,
  citation_count integer,
  source_kind text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
  bounded_limit integer;
  cursor_created_at timestamptz;
  cursor_id uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_memory:authorization_rejected';
  END IF;

  IF p_conversation_id IS NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  bounded_limit := LEAST(GREATEST(COALESCE(p_limit, 50), 1), 100);

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id;

  IF NOT FOUND OR conversation_row.purpose IS DISTINCT FROM 'chat' THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_deleted';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_memory:conversation_forbidden';
  END IF;

  IF p_before_id IS NOT NULL THEN
    SELECT m.created_at, m.id
    INTO cursor_created_at, cursor_id
    FROM app.messages AS m
    WHERE m.id = p_before_id
      AND m.conversation_id = p_conversation_id;

    IF NOT FOUND THEN
      RAISE EXCEPTION 'query_memory:conversation_not_found';
    END IF;
  END IF;

  RETURN QUERY
  SELECT
    page.message_id,
    page.role,
    page.content,
    page.created_at,
    owned.id,
    COALESCE(
      LEAST(COALESCE(counts.company_n, 0) + COALESCE(counts.web_n, 0), 50),
      0
    ),
    CASE
      WHEN COALESCE(counts.company_n, 0) > 0
        AND COALESCE(counts.web_n, 0) > 0
      THEN NULL
      WHEN COALESCE(counts.web_n, 0) > 0 THEN 'web'
      WHEN COALESCE(counts.company_n, 0) > 0 THEN 'company_document'
      ELSE NULL
    END
  FROM (
    SELECT
      m.id AS message_id,
      m.role,
      m.content,
      m.created_at,
      m.run_id,
      m.conversation_id
    FROM app.messages AS m
    WHERE m.conversation_id = p_conversation_id
      AND m.role IN ('user', 'assistant')
      AND (
        p_before_id IS NULL
        OR (m.created_at, m.id) < (cursor_created_at, cursor_id)
      )
    ORDER BY m.created_at DESC, m.id DESC
    LIMIT bounded_limit
  ) AS page
  LEFT JOIN app.runs AS owned
    ON owned.id = page.run_id
   AND owned.conversation_id = page.conversation_id
   AND owned.creator_user_id = caller_user_id
  LEFT JOIN LATERAL (
    SELECT
      (
        SELECT count(*)::integer
        FROM app.citations AS ct
        WHERE ct.run_id = owned.id
      ) AS company_n,
      (
        SELECT count(*)::integer
        FROM app.web_citations AS wc
        WHERE wc.run_id = owned.id
      ) AS web_n
  ) AS counts ON TRUE;
END;
$fn$;

COMMENT ON FUNCTION app.list_conversation_messages_v3(
  uuid, text, bigint, uuid, integer, uuid
) IS
  'Creator-owned transcript page with owned run_id, citation_count 0..50, and nullable source_kind. Mixed company+Web is null. No excerpts.';

REVOKE ALL ON FUNCTION app.list_conversation_messages_v3(
  uuid, text, bigint, uuid, integer, uuid
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.list_conversation_messages_v3(
  uuid, text, bigint, uuid, integer, uuid
) TO app_api;

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
      THEN left(web.src_excerpt, 1000)
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
    SELECT ws.url AS src_url, ws.excerpt AS src_excerpt
    FROM app.web_sources AS ws
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
  'One owned citation with ACL-rechecked company excerpt (1..1000) or HTTPS Web excerpt. Foreign IDs raise not_found.';

REVOKE ALL ON FUNCTION app.get_run_citation_detail_v1(
  uuid, text, bigint, uuid, uuid
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.get_run_citation_detail_v1(
  uuid, text, bigint, uuid, uuid
) TO app_api;
