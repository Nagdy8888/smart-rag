-- A cited chunk is a valid leaf when the span sits in its own raw text.
-- Representative children that contain the span stay preferred, and several
-- of them stay ambiguous. ACL, deletion, and conversation checks are unchanged.

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
  FROM app.document_chunks AS child
  WHERE child.parent_chunk_id = p_chunk_id
    AND child.deleted_at IS NULL
    AND child.is_search_representative IS TRUE
    AND position(bounded_snippet IN child.raw_text) > 0;

  IF match_count > 1 THEN
    RAISE EXCEPTION 'query_citation:leaf_ambiguous';
  END IF;

  IF match_count = 1 THEN
    SELECT
      child.id,
      child.document_id,
      child.version_id,
      child.raw_text,
      child.provenance
    INTO leaf_id, leaf_document, leaf_version, leaf_text, leaf_provenance
    FROM app.document_chunks AS child
    WHERE child.parent_chunk_id = p_chunk_id
      AND child.deleted_at IS NULL
      AND child.is_search_representative IS TRUE
      AND position(bounded_snippet IN child.raw_text) > 0;
  ELSE
    SELECT
      self_row.id,
      self_row.document_id,
      self_row.version_id,
      self_row.raw_text,
      self_row.provenance
    INTO leaf_id, leaf_document, leaf_version, leaf_text, leaf_provenance
    FROM app.document_chunks AS self_row
    WHERE self_row.id = p_chunk_id
      AND self_row.deleted_at IS NULL
      AND position(bounded_snippet IN self_row.raw_text) > 0;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'query_citation:span_not_contained';
    END IF;
  END IF;

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
  'Creator-only insert of one paragraph-mapped PDF citation. One representative child wins; otherwise the cited chunk itself is the leaf when it contains the span. Cap 12. Exact replay is idempotent.';
