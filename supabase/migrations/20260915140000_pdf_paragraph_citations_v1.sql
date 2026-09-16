-- P06-46: paragraph-indexed PDF citations, leaf resolution, and history batching.
-- Expand-only. v1/v2/v3 citation RPC signatures stay unchanged.

DO $preflight$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM app.citations
    GROUP BY run_id, citation_index
    HAVING count(*) > 1
  ) THEN
    RAISE EXCEPTION 'query_citation:duplicate_run_index';
  END IF;
END
$preflight$;

ALTER TABLE app.citations
  ADD COLUMN IF NOT EXISTS paragraph_index integer;

ALTER TABLE app.citations
  DROP CONSTRAINT IF EXISTS citations_paragraph_index_range;

ALTER TABLE app.citations
  ADD CONSTRAINT citations_paragraph_index_range
  CHECK (
    paragraph_index IS NULL
    OR (paragraph_index >= 0 AND paragraph_index <= 5)
  );

COMMENT ON COLUMN app.citations.paragraph_index IS
  'Owning answer paragraph 0..5. NULL on legacy and table-only rows.';

CREATE UNIQUE INDEX IF NOT EXISTS citations_run_index_uq
  ON app.citations (run_id, citation_index);

CREATE OR REPLACE FUNCTION app.pdf_viewer_page_from_locators(
  p_provenance jsonb
)
RETURNS integer
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  pages integer[];
BEGIN
  SELECT array_agg(DISTINCT (loc ->> 'page_index')::integer)
  INTO pages
  FROM jsonb_array_elements(
    CASE
      WHEN jsonb_typeof(p_provenance -> 'locators') = 'array'
      THEN p_provenance -> 'locators'
      ELSE '[]'::jsonb
    END
  ) AS loc
  WHERE (loc ->> 'format') IN ('pdf', 'ocr')
    AND loc ? 'page_index'
    AND (loc ->> 'page_index') ~ '^[0-9]+$';

  IF pages IS NULL OR cardinality(pages) <> 1 THEN
    RETURN NULL;
  END IF;
  RETURN pages[1] + 1;
END;
$fn$;

COMMENT ON FUNCTION app.pdf_viewer_page_from_locators(jsonb) IS
  '1-based PDF viewer page from a single distinct locator page_index. Ignores page_label.';

REVOKE ALL ON FUNCTION app.pdf_viewer_page_from_locators(jsonb)
  FROM PUBLIC, anon, authenticated;

CREATE OR REPLACE FUNCTION app.insert_run_citation_v2(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_citation_index integer,
  p_chunk_id uuid,
  p_snippet text,
  p_paragraph_index integer,
  p_provenance jsonb
)
RETURNS TABLE (citation_id uuid)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  existing app.citations%ROWTYPE;
  bounded_snippet text;
  match_count integer;
  leaf_id uuid;
  leaf_document uuid;
  leaf_version uuid;
  leaf_text text;
  leaf_provenance jsonb;
  viewer_page integer;
  existing_count integer;
  stored_provenance jsonb;
  has_pdf boolean;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_citation:authorization_rejected';
  END IF;

  PERFORM pg_advisory_xact_lock(
    hashtext('smart-rag-citation-insert-v2'),
    hashtext(p_run_id::text)
  );

  IF p_citation_index IS NULL OR p_citation_index < 0 OR p_citation_index > 11 THEN
    RAISE EXCEPTION 'query_citation:answer_bounds_exceeded';
  END IF;

  IF p_paragraph_index IS NOT NULL
     AND (p_paragraph_index < 0 OR p_paragraph_index > 5) THEN
    RAISE EXCEPTION 'query_citation:invalid_paragraph_index';
  END IF;

  IF p_provenance IS NULL THEN
    RAISE EXCEPTION 'query_citation:invalid_provenance';
  END IF;

  IF p_chunk_id IS NULL THEN
    RAISE EXCEPTION 'query_citation:chunk_required';
  END IF;

  bounded_snippet := btrim(coalesce(p_snippet, ''));
  IF bounded_snippet = '' THEN
    RAISE EXCEPTION 'query_citation:citation_span_required';
  END IF;
  IF char_length(bounded_snippet) > 1000 THEN
    RAISE EXCEPTION 'query_citation:answer_bounds_exceeded';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id
  FOR UPDATE;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_citation:run_forbidden';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.conversations AS c
    WHERE c.id = run_row.conversation_id
      AND c.deleted_at IS NULL
      AND c.creator_user_id = caller_user_id
  ) THEN
    RAISE EXCEPTION 'query_citation:conversation_forbidden';
  END IF;

  SELECT count(*)::integer INTO match_count
  FROM (
    SELECT child.id
    FROM app.document_chunks AS child
    WHERE child.parent_chunk_id = p_chunk_id
      AND child.deleted_at IS NULL
      AND child.is_search_representative IS TRUE
      AND position(bounded_snippet IN child.raw_text) > 0
    UNION ALL
    SELECT self_row.id
    FROM app.document_chunks AS self_row
    WHERE self_row.id = p_chunk_id
      AND self_row.deleted_at IS NULL
      AND self_row.is_search_representative IS TRUE
      AND position(bounded_snippet IN self_row.raw_text) > 0
      AND NOT EXISTS (
        SELECT 1
        FROM app.document_chunks AS kids
        WHERE kids.parent_chunk_id = p_chunk_id
          AND kids.deleted_at IS NULL
      )
  ) AS candidates;

  IF match_count = 0 THEN
    RAISE EXCEPTION 'query_citation:span_not_contained';
  END IF;
  IF match_count <> 1 THEN
    RAISE EXCEPTION 'query_citation:leaf_ambiguous';
  END IF;

  SELECT
    resolved.id,
    resolved.document_id,
    resolved.version_id,
    resolved.raw_text,
    resolved.provenance
  INTO leaf_id, leaf_document, leaf_version, leaf_text, leaf_provenance
  FROM (
    SELECT child.id, child.document_id, child.version_id, child.raw_text, child.provenance
    FROM app.document_chunks AS child
    WHERE child.parent_chunk_id = p_chunk_id
      AND child.deleted_at IS NULL
      AND child.is_search_representative IS TRUE
      AND position(bounded_snippet IN child.raw_text) > 0
    UNION ALL
    SELECT self_row.id, self_row.document_id, self_row.version_id, self_row.raw_text, self_row.provenance
    FROM app.document_chunks AS self_row
    WHERE self_row.id = p_chunk_id
      AND self_row.deleted_at IS NULL
      AND self_row.is_search_representative IS TRUE
      AND position(bounded_snippet IN self_row.raw_text) > 0
      AND NOT EXISTS (
        SELECT 1
        FROM app.document_chunks AS kids
        WHERE kids.parent_chunk_id = p_chunk_id
          AND kids.deleted_at IS NULL
      )
  ) AS resolved;

  IF NOT EXISTS (
    SELECT 1
    FROM app.documents AS vis_doc
    INNER JOIN app.document_versions AS vis_ver ON vis_ver.id = leaf_version
    INNER JOIN app.document_chunks AS vis ON vis.id = leaf_id
    WHERE vis_doc.id = leaf_document
      AND vis.deleted_at IS NULL
      AND vis_doc.deleted_at IS NULL
      AND vis_ver.deleted_at IS NULL
      AND vis_doc.current_version_id IS NOT DISTINCT FROM leaf_version
      AND app.caller_can_read_document(
        caller_user_id,
        caller_role,
        vis_doc.id
      )
  ) THEN
    RAISE EXCEPTION 'query_citation:unauthorized_or_missing_passage';
  END IF;

  SELECT EXISTS (
    SELECT 1
    FROM jsonb_array_elements(
      CASE
        WHEN jsonb_typeof(leaf_provenance -> 'locators') = 'array'
        THEN leaf_provenance -> 'locators'
        ELSE '[]'::jsonb
      END
    ) AS loc
    WHERE (loc ->> 'format') IN ('pdf', 'ocr')
  ) INTO has_pdf;

  viewer_page := app.pdf_viewer_page_from_locators(leaf_provenance);
  IF has_pdf AND viewer_page IS NULL THEN
    RAISE EXCEPTION 'query_citation:page_ambiguous';
  END IF;

  stored_provenance := coalesce(p_provenance, '{}'::jsonb)
    || jsonb_build_object(
      'resolved_leaf_id', leaf_id
    );
  IF viewer_page IS NOT NULL THEN
    stored_provenance := stored_provenance
      || jsonb_build_object('page_index', viewer_page - 1);
  END IF;
  stored_provenance := stored_provenance
    - ARRAY['raw_text', 'citation_text', 'excerpt', 'body'];

  SELECT * INTO existing
  FROM app.citations AS ct
  WHERE ct.run_id = p_run_id
    AND ct.citation_index = p_citation_index
  FOR UPDATE;

  IF FOUND THEN
    IF existing.chunk_id IS NOT DISTINCT FROM leaf_id
       AND existing.snippet IS NOT DISTINCT FROM bounded_snippet
       AND existing.paragraph_index IS NOT DISTINCT FROM p_paragraph_index THEN
      citation_id := existing.id;
      RETURN NEXT;
      RETURN;
    END IF;
    RAISE EXCEPTION 'query_citation:replay_conflict';
  END IF;

  SELECT count(*)::integer INTO existing_count
  FROM app.citations
  WHERE run_id = p_run_id;

  IF existing_count >= 12 THEN
    RAISE EXCEPTION 'query_citation:answer_bounds_exceeded';
  END IF;

  INSERT INTO app.citations (
    run_id,
    chunk_id,
    citation_index,
    snippet,
    paragraph_index,
    provenance
  )
  VALUES (
    p_run_id,
    leaf_id,
    p_citation_index,
    bounded_snippet,
    p_paragraph_index,
    stored_provenance
  )
  RETURNING app.citations.id INTO citation_id;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.insert_run_citation_v2(
  uuid, text, bigint, uuid, integer, uuid, text, integer, jsonb
) IS
  'Creator-only insert of one paragraph-mapped PDF citation. Resolves one leaf containing the exact span. Cap 12. Exact replay is idempotent.';

REVOKE ALL ON FUNCTION app.insert_run_citation_v2(
  uuid, text, bigint, uuid, integer, uuid, text, integer, jsonb
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.insert_run_citation_v2(
  uuid, text, bigint, uuid, integer, uuid, text, integer, jsonb
) TO app_api;

CREATE OR REPLACE FUNCTION app.list_run_citations_v4(
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
  source_unavailable boolean,
  source_kind text,
  web_source_id uuid,
  paragraph_index integer,
  document_title text,
  pdf_page_number integer,
  evidence_excerpt text
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
            'page_number', cited.stored_page_number,
            'page_label', cited.page_label,
            'section_path', CASE
              WHEN cited.section_path IS NULL
                OR cardinality(cited.section_path) = 0
              THEN NULL
              ELSE to_jsonb(cited.section_path)
            END,
            'document_id', cited.document_id,
            'document_title', cited.live_title,
            'source_kind', 'company_document',
            'pdf_page_number', cited.viewer_page
          )
        )
      ELSE
        (cited.provenance - ARRAY[
          'page_number',
          'page_label',
          'section_path',
          'document_title',
          'document_id',
          'sheet_name',
          'range_ref',
          'source_url',
          'pdf_page_number',
          'resolved_leaf_id',
          'page_index'
        ]) || jsonb_build_object('source_kind', 'company_document')
    END,
    (
      cited.source_unavailable
      OR (cited.chunk_id IS NOT NULL AND NOT cited.recheck_ok)
    ) AS source_unavailable,
    'company_document'::text,
    NULL::uuid,
    cited.paragraph_index,
    CASE WHEN cited.recheck_ok THEN cited.live_title ELSE NULL END,
    CASE WHEN cited.recheck_ok THEN cited.viewer_page ELSE NULL END,
    CASE
      WHEN cited.recheck_ok
        AND cited.snippet IS NOT NULL
        AND btrim(cited.snippet) <> ''
        AND position(cited.snippet IN coalesce(cited.raw_text, '')) > 0
      THEN left(cited.snippet, 1000)
      ELSE NULL
    END
  FROM (
    SELECT
      ct.id,
      ct.citation_index,
      ct.chunk_id,
      ct.provenance,
      ct.source_unavailable,
      ct.paragraph_index,
      ct.snippet,
      dc.page_number AS stored_page_number,
      dc.raw_text,
      dc.section_path,
      dc.document_id,
      d.title AS live_title,
      CASE
        WHEN jsonb_typeof(dc.provenance -> 'locators') = 'array' THEN (
          SELECT nullif(btrim(loc ->> 'page_label'), '')
          FROM jsonb_array_elements(dc.provenance -> 'locators') AS loc
          WHERE nullif(btrim(loc ->> 'page_label'), '') IS NOT NULL
          LIMIT 1
        )
        ELSE NULL
      END AS page_label,
      app.pdf_viewer_page_from_locators(dc.provenance) AS viewer_page,
      (
        ct.chunk_id IS NULL
        OR (
          EXISTS (
            SELECT 1
            FROM app.document_chunks AS vis
            INNER JOIN app.documents AS vis_doc ON vis_doc.id = vis.document_id
            INNER JOIN app.document_versions AS vis_ver
              ON vis_ver.id = vis.version_id
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
          AND (
            NOT EXISTS (
              SELECT 1
              FROM jsonb_array_elements(
                CASE
                  WHEN jsonb_typeof(dc.provenance -> 'locators') = 'array'
                  THEN dc.provenance -> 'locators'
                  ELSE '[]'::jsonb
                END
              ) AS loc
              WHERE (loc ->> 'format') IN ('pdf', 'ocr')
            )
            OR app.pdf_viewer_page_from_locators(dc.provenance) IS NOT NULL
          )
          AND (
            ct.snippet IS NULL
            OR btrim(ct.snippet) = ''
            OR position(ct.snippet IN coalesce(dc.raw_text, '')) > 0
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
  UNION ALL
  SELECT
    wc.id,
    wc.citation_index,
    NULL::uuid,
    jsonb_build_object(
      'source_kind', 'web',
      'url', ws.url,
      'title', ws.title,
      'content_hash', ws.content_hash
    ),
    false,
    'web'::text,
    ws.id,
    NULL::integer,
    NULL::text,
    NULL::integer,
    NULL::text
  FROM app.web_citations AS wc
  INNER JOIN app.web_sources AS ws ON ws.id = wc.web_source_id
  WHERE wc.run_id = p_run_id
  ORDER BY 6, 2
  LIMIT 62;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_citations_v4(uuid, text, bigint, uuid) IS
  'Creator-only citations with paragraph_index, live title, PDF viewer page, and ACL-checked excerpt. page_label never drives pdf_page_number.';

REVOKE ALL ON FUNCTION app.list_run_citations_v4(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.list_run_citations_v4(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.list_conversation_messages_v2(
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
  run_id uuid
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
    m.id,
    m.role,
    m.content,
    m.created_at,
    m.run_id
  FROM app.messages AS m
  WHERE m.conversation_id = p_conversation_id
    AND m.role IN ('user', 'assistant')
    AND (
      p_before_id IS NULL
      OR (m.created_at, m.id) < (cursor_created_at, cursor_id)
    )
  ORDER BY m.created_at DESC, m.id DESC
  LIMIT bounded_limit;
END;
$fn$;

COMMENT ON FUNCTION app.list_conversation_messages_v2(
  uuid, text, bigint, uuid, integer, uuid
) IS
  'Creator-owned transcript page with nullable run_id. Full content. Untrusted data.';

REVOKE ALL ON FUNCTION app.list_conversation_messages_v2(
  uuid, text, bigint, uuid, integer, uuid
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_conversation_messages_v2(
  uuid, text, bigint, uuid, integer, uuid
) TO app_api;

CREATE OR REPLACE FUNCTION app.list_conversation_citations_v1(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid,
  p_run_ids uuid[]
)
RETURNS TABLE (
  run_id uuid,
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
  evidence_excerpt text
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  bounded uuid[];
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF p_conversation_id IS NULL THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.conversations AS c
    WHERE c.id = p_conversation_id
      AND c.deleted_at IS NULL
      AND c.creator_user_id = caller_user_id
      AND c.purpose IS NOT DISTINCT FROM 'chat'
  ) THEN
    RAISE EXCEPTION 'query_memory:conversation_not_found';
  END IF;

  IF p_run_ids IS NULL OR cardinality(p_run_ids) = 0 THEN
    RETURN;
  END IF;

  IF cardinality(p_run_ids) > 50 THEN
    RAISE EXCEPTION 'query_citation:batch_cap';
  END IF;

  SELECT array_agg(DISTINCT owned.id)
  INTO bounded
  FROM unnest(p_run_ids) AS requested(id)
  INNER JOIN app.runs AS owned ON owned.id = requested.id
  INNER JOIN app.conversations AS c ON c.id = owned.conversation_id
  WHERE owned.conversation_id = p_conversation_id
    AND owned.creator_user_id = caller_user_id
    AND c.deleted_at IS NULL
    AND c.creator_user_id = caller_user_id;

  IF bounded IS NULL THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    owned_run,
    listed.citation_id,
    listed.citation_index,
    listed.chunk_id,
    listed.provenance,
    listed.source_unavailable,
    listed.source_kind,
    listed.web_source_id,
    listed.paragraph_index,
    listed.document_title,
    listed.pdf_page_number,
    listed.evidence_excerpt
  FROM unnest(bounded) AS owned_run
  CROSS JOIN LATERAL app.list_run_citations_v4(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    owned_run
  ) AS listed;
END;
$fn$;

COMMENT ON FUNCTION app.list_conversation_citations_v1(
  uuid, text, bigint, uuid, uuid[]
) IS
  'Creator-only citation batch for at most 50 owned run IDs on one conversation. Foreign IDs are omitted.';

REVOKE ALL ON FUNCTION app.list_conversation_citations_v1(
  uuid, text, bigint, uuid, uuid[]
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.list_conversation_citations_v1(
  uuid, text, bigint, uuid, uuid[]
) TO app_api;
