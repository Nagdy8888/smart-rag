-- Run-scoped public Web evidence. Parallel to app.citations; never mixed
-- into company ACL chunk recheck. RLS deny-by-default. app_api RPCs only.

CREATE TABLE app.web_research_operations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES app.runs (id) ON DELETE CASCADE,
  operation_key text NOT NULL,
  kind text NOT NULL,
  request_hash text NOT NULL,
  status text NOT NULL,
  attempts integer NOT NULL DEFAULT 0,
  provider_request_id text,
  failure_reason text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT web_research_operations_key_chk CHECK (
    char_length(operation_key) BETWEEN 8 AND 128
  ),
  CONSTRAINT web_research_operations_kind_chk CHECK (
    kind IN ('search', 'contents', 'fetch')
  ),
  CONSTRAINT web_research_operations_hash_chk CHECK (
    request_hash ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT web_research_operations_status_chk CHECK (
    status IN ('planned', 'sent', 'succeeded', 'failed', 'ambiguous')
  ),
  CONSTRAINT web_research_operations_attempts_chk CHECK (
    attempts BETWEEN 0 AND 2
  ),
  CONSTRAINT web_research_operations_key_run_uq UNIQUE (run_id, operation_key)
);

CREATE TABLE app.web_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES app.runs (id) ON DELETE CASCADE,
  source_index integer NOT NULL,
  url text NOT NULL,
  title text NOT NULL DEFAULT '',
  excerpt text NOT NULL,
  content_hash text NOT NULL,
  published_date text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT web_sources_index_chk CHECK (source_index BETWEEN 0 AND 5),
  CONSTRAINT web_sources_url_len_chk CHECK (char_length(url) BETWEEN 1 AND 2048),
  CONSTRAINT web_sources_url_scheme_chk CHECK (url ~* '^https?://'),
  CONSTRAINT web_sources_url_fragment_chk CHECK (position('#' IN url) = 0),
  CONSTRAINT web_sources_url_userinfo_chk CHECK (url !~* '://[^/]*@'),
  CONSTRAINT web_sources_title_chk CHECK (char_length(title) <= 512),
  CONSTRAINT web_sources_excerpt_chk CHECK (
    char_length(excerpt) BETWEEN 1 AND 8000
  ),
  CONSTRAINT web_sources_hash_chk CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  CONSTRAINT web_sources_run_index_uq UNIQUE (run_id, source_index),
  CONSTRAINT web_sources_run_url_uq UNIQUE (run_id, url)
);

CREATE TABLE app.web_citations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES app.runs (id) ON DELETE CASCADE,
  web_source_id uuid NOT NULL REFERENCES app.web_sources (id) ON DELETE CASCADE,
  citation_index integer NOT NULL,
  span text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT web_citations_index_chk CHECK (citation_index BETWEEN 0 AND 11),
  CONSTRAINT web_citations_span_chk CHECK (char_length(span) BETWEEN 1 AND 1000),
  CONSTRAINT web_citations_run_index_uq UNIQUE (run_id, citation_index)
);

CREATE INDEX web_research_operations_run_idx
  ON app.web_research_operations (run_id);
CREATE INDEX web_sources_run_idx ON app.web_sources (run_id);
CREATE INDEX web_citations_run_idx ON app.web_citations (run_id);
CREATE INDEX web_citations_source_idx ON app.web_citations (web_source_id);

COMMENT ON TABLE app.web_research_operations IS
  'Idempotent Exa/crawl-proxy operations for one query run. Same key+hash replays; sent-without-terminal is ambiguous.';
COMMENT ON TABLE app.web_sources IS
  'Creator-owned public Web excerpts for one query run. Never company RAG evidence.';
COMMENT ON TABLE app.web_citations IS
  'Verified Web citation spans bound to persisted web_sources. API listing omits excerpt and span.';

ALTER TABLE app.web_research_operations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.web_research_operations FORCE ROW LEVEL SECURITY;
ALTER TABLE app.web_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.web_sources FORCE ROW LEVEL SECURITY;
ALTER TABLE app.web_citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.web_citations FORCE ROW LEVEL SECURITY;

CREATE POLICY web_research_operations_postgres_all
  ON app.web_research_operations FOR ALL TO postgres
  USING (true) WITH CHECK (true);
CREATE POLICY web_sources_postgres_all
  ON app.web_sources FOR ALL TO postgres
  USING (true) WITH CHECK (true);
CREATE POLICY web_citations_postgres_all
  ON app.web_citations FOR ALL TO postgres
  USING (true) WITH CHECK (true);

REVOKE ALL ON TABLE app.web_research_operations
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON TABLE app.web_sources
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON TABLE app.web_citations
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
GRANT ALL ON TABLE app.web_research_operations TO postgres;
GRANT ALL ON TABLE app.web_sources TO postgres;
GRANT ALL ON TABLE app.web_citations TO postgres;

CREATE OR REPLACE FUNCTION app._web_require_run_owner(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS app.runs
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'web_evidence:authorization_rejected';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'web_evidence:not_found';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.conversations AS c
    WHERE c.id = run_row.conversation_id
      AND c.deleted_at IS NULL
      AND c.creator_user_id = caller_user_id
  ) THEN
    RAISE EXCEPTION 'web_evidence:not_found';
  END IF;

  RETURN run_row;
END;
$fn$;

REVOKE ALL ON FUNCTION app._web_require_run_owner(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;

CREATE OR REPLACE FUNCTION app.begin_web_research_operation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_operation_key text,
  p_kind text,
  p_request_hash text
)
RETURNS TABLE (operation_id uuid, status text, replayed boolean)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  existing app.web_research_operations%ROWTYPE;
  inserted_id uuid;
BEGIN
  PERFORM app._web_require_run_owner(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );

  SELECT * INTO existing
  FROM app.web_research_operations AS op
  WHERE op.run_id = p_run_id
    AND op.operation_key = p_operation_key
  FOR UPDATE;

  IF FOUND THEN
    IF existing.request_hash IS DISTINCT FROM p_request_hash THEN
      RAISE EXCEPTION 'web_operation:conflict';
    END IF;
    IF existing.status = 'sent' THEN
      RAISE EXCEPTION 'web_operation:ambiguous';
    END IF;
    operation_id := existing.id;
    status := existing.status;
    replayed := true;
    RETURN NEXT;
    RETURN;
  END IF;

  INSERT INTO app.web_research_operations (
    run_id, operation_key, kind, request_hash, status, attempts
  )
  VALUES (
    p_run_id, p_operation_key, p_kind, p_request_hash, 'planned', 0
  )
  RETURNING id INTO inserted_id;

  operation_id := inserted_id;
  status := 'planned';
  replayed := false;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.mark_web_research_operation_sent(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_operation_id uuid
)
RETURNS TABLE (operation_id uuid, status text, attempts integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  existing app.web_research_operations%ROWTYPE;
BEGIN
  SELECT * INTO existing
  FROM app.web_research_operations AS op
  WHERE op.id = p_operation_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'web_evidence:not_found';
  END IF;

  PERFORM app._web_require_run_owner(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    existing.run_id
  );

  IF existing.status IN ('succeeded', 'failed') THEN
    operation_id := existing.id;
    status := existing.status;
    attempts := existing.attempts;
    RETURN NEXT;
    RETURN;
  END IF;

  IF existing.status = 'sent' THEN
    RAISE EXCEPTION 'web_operation:ambiguous';
  END IF;

  IF existing.status IS DISTINCT FROM 'planned' THEN
    RAISE EXCEPTION 'web_operation:conflict';
  END IF;

  IF existing.attempts >= 2 THEN
    RAISE EXCEPTION 'web_operation:ambiguous';
  END IF;

  UPDATE app.web_research_operations
  SET status = 'sent',
      attempts = existing.attempts + 1,
      updated_at = timezone('utc', now())
  WHERE id = existing.id
  RETURNING
    app.web_research_operations.id,
    app.web_research_operations.status,
    app.web_research_operations.attempts
  INTO operation_id, status, attempts;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.complete_web_research_operation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_operation_id uuid,
  p_ok boolean,
  p_provider_request_id text,
  p_failure_reason text
)
RETURNS TABLE (operation_id uuid, status text)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  existing app.web_research_operations%ROWTYPE;
  next_status text;
BEGIN
  SELECT * INTO existing
  FROM app.web_research_operations AS op
  WHERE op.id = p_operation_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'web_evidence:not_found';
  END IF;

  PERFORM app._web_require_run_owner(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    existing.run_id
  );

  IF existing.status IN ('succeeded', 'failed') THEN
    operation_id := existing.id;
    status := existing.status;
    RETURN NEXT;
    RETURN;
  END IF;

  IF existing.status IS DISTINCT FROM 'sent' THEN
    RAISE EXCEPTION 'web_operation:conflict';
  END IF;

  next_status := CASE WHEN p_ok THEN 'succeeded' ELSE 'failed' END;

  UPDATE app.web_research_operations
  SET status = next_status,
      provider_request_id = left(coalesce(p_provider_request_id, ''), 128),
      failure_reason = left(coalesce(p_failure_reason, ''), 64),
      updated_at = timezone('utc', now())
  WHERE id = existing.id
  RETURNING
    app.web_research_operations.id,
    app.web_research_operations.status
  INTO operation_id, status;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.insert_web_source(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_source_index integer,
  p_url text,
  p_title text,
  p_excerpt text,
  p_content_hash text,
  p_published_date text
)
RETURNS TABLE (web_source_id uuid)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  inserted_id uuid;
  computed_hash text;
  source_count integer;
BEGIN
  PERFORM app._web_require_run_owner(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );

  IF p_source_index IS NULL OR p_source_index < 0 OR p_source_index > 5 THEN
    RAISE EXCEPTION 'web_evidence:invalid_index';
  END IF;

  SELECT count(*) INTO source_count
  FROM app.web_sources
  WHERE run_id = p_run_id;

  IF source_count >= 6 THEN
    RAISE EXCEPTION 'web_evidence:cap_exceeded';
  END IF;

  IF p_url IS NULL
     OR char_length(p_url) NOT BETWEEN 1 AND 2048
     OR p_url !~* '^https?://'
     OR position('#' IN p_url) > 0
     OR p_url ~* '://[^/]*@' THEN
    RAISE EXCEPTION 'web_evidence:invalid_url';
  END IF;

  IF p_excerpt IS NULL OR char_length(p_excerpt) NOT BETWEEN 1 AND 8000 THEN
    RAISE EXCEPTION 'web_evidence:invalid_excerpt';
  END IF;

  computed_hash := encode(sha256(convert_to(p_excerpt, 'UTF8')), 'hex');
  IF p_content_hash IS DISTINCT FROM computed_hash THEN
    RAISE EXCEPTION 'web_evidence:invalid_hash';
  END IF;

  INSERT INTO app.web_sources (
    run_id, source_index, url, title, excerpt, content_hash, published_date
  )
  VALUES (
    p_run_id,
    p_source_index,
    p_url,
    left(coalesce(p_title, ''), 512),
    p_excerpt,
    p_content_hash,
    left(nullif(p_published_date, ''), 64)
  )
  RETURNING id INTO inserted_id;

  web_source_id := inserted_id;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.insert_web_citation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_citation_index integer,
  p_web_source_id uuid,
  p_span text
)
RETURNS TABLE (web_citation_id uuid)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  source_row app.web_sources%ROWTYPE;
  inserted_id uuid;
  citation_count integer;
BEGIN
  PERFORM app._web_require_run_owner(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id
  );

  IF p_citation_index IS NULL
     OR p_citation_index < 0
     OR p_citation_index > 11 THEN
    RAISE EXCEPTION 'web_evidence:invalid_index';
  END IF;

  IF p_span IS NULL OR char_length(p_span) NOT BETWEEN 1 AND 1000 THEN
    RAISE EXCEPTION 'web_evidence:invalid_span';
  END IF;

  SELECT * INTO source_row
  FROM app.web_sources
  WHERE id = p_web_source_id;

  IF NOT FOUND OR source_row.run_id IS DISTINCT FROM p_run_id THEN
    RAISE EXCEPTION 'web_evidence:not_found';
  END IF;

  IF position(p_span IN source_row.excerpt) = 0 THEN
    RAISE EXCEPTION 'web_evidence:span_not_contained';
  END IF;

  SELECT count(*) INTO citation_count
  FROM app.web_citations
  WHERE run_id = p_run_id;

  IF citation_count >= 12 THEN
    RAISE EXCEPTION 'web_evidence:cap_exceeded';
  END IF;

  INSERT INTO app.web_citations (
    run_id, web_source_id, citation_index, span
  )
  VALUES (
    p_run_id, p_web_source_id, p_citation_index, p_span
  )
  RETURNING id INTO inserted_id;

  web_citation_id := inserted_id;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.list_run_citations_v3(
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
  web_source_id uuid
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
            'page_label', cited.page_label,
            'section_path', CASE
              WHEN cited.section_path IS NULL
                OR cardinality(cited.section_path) = 0
              THEN NULL
              ELSE to_jsonb(cited.section_path)
            END,
            'document_id', cited.document_id,
            'document_title', cited.document_title,
            'source_kind', 'company_document'
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
          'source_url'
        ]) || jsonb_build_object('source_kind', 'company_document')
    END,
    (
      cited.source_unavailable
      OR (cited.chunk_id IS NOT NULL AND NOT cited.recheck_ok)
    ) AS source_unavailable,
    'company_document'::text,
    NULL::uuid
  FROM (
    SELECT
      ct.id,
      ct.citation_index,
      ct.chunk_id,
      ct.provenance,
      ct.source_unavailable,
      dc.page_number,
      CASE
        WHEN jsonb_typeof(dc.provenance -> 'locators') = 'array' THEN (
          SELECT nullif(btrim(loc ->> 'page_label'), '')
          FROM jsonb_array_elements(dc.provenance -> 'locators') AS loc
          WHERE nullif(btrim(loc ->> 'page_label'), '') IS NOT NULL
          LIMIT 1
        )
        ELSE NULL
      END AS page_label,
      dc.section_path,
      dc.document_id,
      d.title AS document_title,
      (
        ct.chunk_id IS NULL
        OR EXISTS (
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
    ws.id
  FROM app.web_citations AS wc
  INNER JOIN app.web_sources AS ws ON ws.id = wc.web_source_id
  WHERE wc.run_id = p_run_id
  ORDER BY 6, 2
  LIMIT 62;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_citations_v3(uuid, text, bigint, uuid) IS
  'Creator-only merged company and Web citations. Company ACL/current-version recheck matches v2. Web rows return URL/title/hash only; excerpt and span are omitted.';

REVOKE ALL ON FUNCTION app.begin_web_research_operation(
  uuid, text, bigint, uuid, text, text, text
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.begin_web_research_operation(
  uuid, text, bigint, uuid, text, text, text
) TO app_api;

REVOKE ALL ON FUNCTION app.mark_web_research_operation_sent(
  uuid, text, bigint, uuid
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.mark_web_research_operation_sent(
  uuid, text, bigint, uuid
) TO app_api;

REVOKE ALL ON FUNCTION app.complete_web_research_operation(
  uuid, text, bigint, uuid, boolean, text, text
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.complete_web_research_operation(
  uuid, text, bigint, uuid, boolean, text, text
) TO app_api;

REVOKE ALL ON FUNCTION app.insert_web_source(
  uuid, text, bigint, uuid, integer, text, text, text, text, text
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.insert_web_source(
  uuid, text, bigint, uuid, integer, text, text, text, text, text
) TO app_api;

REVOKE ALL ON FUNCTION app.insert_web_citation(
  uuid, text, bigint, uuid, integer, uuid, text
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.insert_web_citation(
  uuid, text, bigint, uuid, integer, uuid, text
) TO app_api;

REVOKE ALL ON FUNCTION app.list_run_citations_v3(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.list_run_citations_v3(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.search_conversation_lingering_ids(
  p_conversation_id uuid
)
RETURNS TABLE (relation_name text, match_count bigint)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app, langgraph
AS $fn$
DECLARE
  v_id text := p_conversation_id::text;
BEGIN
  RETURN QUERY
  SELECT 'app.messages'::text, count(*)::bigint
  FROM app.messages
  WHERE conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.runs'::text, count(*)::bigint
  FROM app.runs
  WHERE conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.run_events'::text, count(*)::bigint
  FROM app.run_events AS e
  INNER JOIN app.runs AS r ON r.id = e.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.citations'::text, count(*)::bigint
  FROM app.citations AS c
  INNER JOIN app.runs AS r ON r.id = c.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.web_research_operations'::text, count(*)::bigint
  FROM app.web_research_operations AS op
  INNER JOIN app.runs AS r ON r.id = op.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.web_sources'::text, count(*)::bigint
  FROM app.web_sources AS ws
  INNER JOIN app.runs AS r ON r.id = ws.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.web_citations'::text, count(*)::bigint
  FROM app.web_citations AS wc
  INNER JOIN app.runs AS r ON r.id = wc.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'app.user_feedback'::text, count(*)::bigint
  FROM app.user_feedback AS f
  INNER JOIN app.runs AS r ON r.id = f.run_id
  WHERE r.conversation_id = p_conversation_id
  UNION ALL
  SELECT 'langgraph.checkpoints'::text, count(*)::bigint
  FROM langgraph.checkpoints
  WHERE thread_id = v_id
  UNION ALL
  SELECT 'langgraph.checkpoint_blobs'::text, count(*)::bigint
  FROM langgraph.checkpoint_blobs
  WHERE thread_id = v_id
  UNION ALL
  SELECT 'langgraph.checkpoint_writes'::text, count(*)::bigint
  FROM langgraph.checkpoint_writes
  WHERE thread_id = v_id
  UNION ALL
  SELECT 'langgraph.store'::text, count(*)::bigint
  FROM langgraph.store
  WHERE prefix LIKE '%.' || v_id
     OR prefix = v_id
     OR prefix LIKE v_id || '.%';
END;
$fn$;

CREATE OR REPLACE FUNCTION app.delete_conversation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app, langgraph
AS $fn$
DECLARE
  conversation_row app.conversations%ROWTYPE;
  v_id text;
  v_run_hashes text[] := '{}'::text[];
  v_now timestamptz := timezone('utc', now());
  v_role app.user_role;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  SELECT * INTO conversation_row
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.creator_user_id IS DISTINCT FROM caller_user_id
    AND caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'conversation:not_found';
  END IF;

  IF conversation_row.deleted_at IS NOT NULL THEN
    RETURN;
  END IF;

  v_id := p_conversation_id::text;
  v_role := caller_role::app.user_role;

  UPDATE app.conversations
  SET deleted_at = v_now
  WHERE id = p_conversation_id
    AND deleted_at IS NULL;

  SELECT coalesce(array_agg(encode(sha256(convert_to(r.id::text, 'UTF8')), 'hex')), '{}')
  INTO v_run_hashes
  FROM app.runs AS r
  WHERE r.conversation_id = p_conversation_id;

  DELETE FROM app.messages WHERE conversation_id = p_conversation_id;
  DELETE FROM app.user_feedback AS f
    USING app.runs AS r
    WHERE f.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.web_citations AS wc
    USING app.runs AS r
    WHERE wc.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.web_sources AS ws
    USING app.runs AS r
    WHERE ws.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.web_research_operations AS op
    USING app.runs AS r
    WHERE op.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.citations AS c
    USING app.runs AS r
    WHERE c.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.run_events AS e
    USING app.runs AS r
    WHERE e.run_id = r.id AND r.conversation_id = p_conversation_id;
  DELETE FROM app.runs WHERE conversation_id = p_conversation_id;

  DELETE FROM langgraph.checkpoint_writes WHERE thread_id = v_id;
  DELETE FROM langgraph.checkpoint_blobs WHERE thread_id = v_id;
  DELETE FROM langgraph.checkpoints WHERE thread_id = v_id;
  DELETE FROM langgraph.store
  WHERE prefix LIKE '%.' || v_id
     OR prefix = v_id
     OR prefix LIKE v_id || '.%';

  PERFORM app.append_audit_event(
    'conversation_deleted',
    caller_user_id,
    v_role,
    'conversation',
    p_conversation_id,
    caller_authorization_version,
    jsonb_build_object(
      'conversation_id', p_conversation_id,
      'run_id_hashes', to_jsonb(v_run_hashes),
      'audited_privileged', caller_role IN ('owner', 'admin')
        AND conversation_row.creator_user_id IS DISTINCT FROM caller_user_id
    )
  );

  INSERT INTO app.langsmith_deletion_requests (
    conversation_id_hash,
    run_id_hashes,
    hashed_trace_keys,
    status,
    sla_deadline_at,
    retry_at
  )
  VALUES (
    encode(sha256(convert_to(v_id, 'UTF8')), 'hex'),
    v_run_hashes,
    v_run_hashes,
    'pending',
    v_now + interval '24 hours',
    v_now
  );
END;
$fn$;
