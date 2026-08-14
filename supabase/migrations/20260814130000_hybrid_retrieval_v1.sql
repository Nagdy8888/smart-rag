-- Phase 4 Packet 2: HNSW/trigram/metadata indexes and security-invoker
-- dense/term/recheck RPCs. Authorization predicates live inside SQL.
-- Do not install pg_search on managed Supabase.

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA extensions;

GRANT USAGE ON SCHEMA extensions TO app_api;
GRANT USAGE ON SCHEMA search TO app_api;
GRANT EXECUTE ON FUNCTION search.normalize_arabic_v1(text) TO app_api;
GRANT EXECUTE ON FUNCTION search.arabic_normalization_version() TO app_api;

GRANT SELECT ON app.document_search_terms TO app_api;
GRANT SELECT ON app.search_aliases TO app_api;

DROP POLICY IF EXISTS document_search_terms_api_read ON app.document_search_terms;
CREATE POLICY document_search_terms_api_read
  ON app.document_search_terms
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS search_aliases_api_read ON app.search_aliases;
CREATE POLICY search_aliases_api_read
  ON app.search_aliases
  FOR SELECT
  TO app_api
  USING (true);

CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
  ON app.document_chunks
  USING hnsw (embedding extensions.vector_cosine_ops)
  WITH (m = 16, ef_construction = 64)
  WHERE deleted_at IS NULL AND embedding IS NOT NULL;

COMMENT ON INDEX app.document_chunks_embedding_hnsw_idx IS
  'Filtered HNSW cosine index over contextual embeddings. Citations use raw_text.';

CREATE INDEX IF NOT EXISTS document_search_terms_term_trgm_idx
  ON app.document_search_terms
  USING gin (term_normalized extensions.gin_trgm_ops);

CREATE INDEX IF NOT EXISTS search_aliases_alias_trgm_idx
  ON app.search_aliases
  USING gin (alias_normalized extensions.gin_trgm_ops);

CREATE INDEX IF NOT EXISTS document_versions_language_current_idx
  ON app.document_versions (language)
  WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS document_acl_grantee_active_idx
  ON app.document_acl (grantee_user_id, document_id)
  WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS document_chunks_retrievable_idx
  ON app.document_chunks (document_id, version_id)
  WHERE deleted_at IS NULL
    AND is_search_representative
    AND embedding IS NOT NULL;

CREATE OR REPLACE FUNCTION app.retrieval_exact_row_cap()
RETURNS integer
LANGUAGE sql
IMMUTABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT 10000;
$$;

COMMENT ON FUNCTION app.retrieval_exact_row_cap() IS
  'Hard authorized-row ceiling for exact dense fallback. Planner estimates are not this cap.';

CREATE OR REPLACE FUNCTION app.count_authorized_retrievable_chunks(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_language text DEFAULT NULL
)
RETURNS integer
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
DECLARE
  authorized_count integer;
BEGIN
  IF p_language IS NOT NULL AND p_language NOT IN ('en', 'ar', 'mixed') THEN
    RAISE EXCEPTION 'unknown_language';
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN 0;
  END IF;

  SELECT count(*)::integer
  INTO authorized_count
  FROM app.document_chunks AS c
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND c.embedding IS NOT NULL
    AND c.is_search_representative
    AND dv.status IN (
      'hybrid_ready'::app.document_status,
      'graph_pending'::app.document_status,
      'graph_ready'::app.document_status,
      'graph_ineligible'::app.document_status
    )
    AND (p_language IS NULL OR dv.language IS NOT DISTINCT FROM p_language)
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id);

  RETURN COALESCE(authorized_count, 0);
END;
$fn$;

COMMENT ON FUNCTION app.count_authorized_retrievable_chunks(uuid, text, bigint, text) IS
  'Counts ACL-visible current Hybrid chunks before exact fallback admission.';

CREATE OR REPLACE FUNCTION app.retrieve_dense_candidates(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_query_embedding extensions.vector,
  p_profile text,
  p_mode text,
  p_candidate_limit integer,
  p_language text DEFAULT NULL
)
RETURNS TABLE (
  chunk_id uuid,
  document_id uuid,
  version_id uuid,
  distance double precision,
  retrieval_mode text
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
DECLARE
  capped_limit integer;
  authorized_count integer;
  exact_cap integer;
BEGIN
  IF p_profile IS DISTINCT FROM 'low'
     AND p_profile IS DISTINCT FROM 'medium'
     AND p_profile IS DISTINCT FROM 'high' THEN
    RAISE EXCEPTION 'unknown_retrieval_profile';
  END IF;

  IF p_mode IS DISTINCT FROM 'ann' AND p_mode IS DISTINCT FROM 'exact' THEN
    RAISE EXCEPTION 'unknown_retrieval_mode';
  END IF;

  IF p_language IS NOT NULL AND p_language NOT IN ('en', 'ar', 'mixed') THEN
    RAISE EXCEPTION 'unknown_language';
  END IF;

  IF p_query_embedding IS NULL THEN
    RAISE EXCEPTION 'missing_query_embedding';
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  capped_limit := LEAST(GREATEST(COALESCE(p_candidate_limit, 1), 1), 100);

  PERFORM set_config('hnsw.iterative_scan', 'strict_order', true);
  PERFORM set_config('hnsw.scan_mem_multiplier', '2', true);
  PERFORM set_config('work_mem', '32MB', true);
  PERFORM set_config('statement_timeout', '8000', true);

  IF p_profile = 'low' THEN
    PERFORM set_config('hnsw.ef_search', '40', true);
    PERFORM set_config('hnsw.max_scan_tuples', '8000', true);
  ELSIF p_profile = 'medium' THEN
    PERFORM set_config('hnsw.ef_search', '80', true);
    PERFORM set_config('hnsw.max_scan_tuples', '16000', true);
  ELSE
    PERFORM set_config('hnsw.ef_search', '120', true);
    PERFORM set_config('hnsw.max_scan_tuples', '20000', true);
  END IF;

  IF p_mode = 'exact' THEN
    exact_cap := app.retrieval_exact_row_cap();
    authorized_count := app.count_authorized_retrievable_chunks(
      caller_user_id,
      caller_role,
      caller_authorization_version,
      p_language
    );
    IF authorized_count > exact_cap THEN
      RETURN;
    END IF;
    PERFORM set_config('enable_indexscan', 'off', true);
    PERFORM set_config('enable_bitmapscan', 'off', true);
  END IF;

  RETURN QUERY
  SELECT
    c.id,
    c.document_id,
    c.version_id,
    (c.embedding <=> p_query_embedding)::double precision,
    p_mode
  FROM app.document_chunks AS c
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND c.embedding IS NOT NULL
    AND c.is_search_representative
    AND dv.status IN (
      'hybrid_ready'::app.document_status,
      'graph_pending'::app.document_status,
      'graph_ready'::app.document_status,
      'graph_ineligible'::app.document_status
    )
    AND (p_language IS NULL OR dv.language IS NOT DISTINCT FROM p_language)
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ORDER BY c.embedding <=> p_query_embedding, c.id ASC
  LIMIT capped_limit;
END;
$fn$;

COMMENT ON FUNCTION app.retrieve_dense_candidates(
  uuid, text, bigint, extensions.vector, text, text, integer, text
) IS
  'Security-invoker dense ANN/exact candidates. Filters before rank/limit. SET LOCAL HNSW.';

CREATE OR REPLACE FUNCTION app.retrieve_term_candidates(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_query_normalized text,
  p_candidate_limit integer,
  p_language text DEFAULT NULL
)
RETURNS TABLE (
  chunk_id uuid,
  document_id uuid,
  version_id uuid,
  match_kind text,
  similarity double precision
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
DECLARE
  capped_limit integer;
BEGIN
  IF p_language IS NOT NULL AND p_language NOT IN ('en', 'ar', 'mixed') THEN
    RAISE EXCEPTION 'unknown_language';
  END IF;

  IF p_query_normalized IS NULL OR btrim(p_query_normalized) = '' THEN
    RETURN;
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  capped_limit := LEAST(GREATEST(COALESCE(p_candidate_limit, 1), 1), 30);
  PERFORM set_config('statement_timeout', '8000', true);
  PERFORM set_config('pg_trgm.similarity_threshold', '0.3', true);

  RETURN QUERY
  WITH retrievable AS (
    SELECT
      c.id AS chunk_id,
      c.document_id,
      c.version_id
    FROM app.document_chunks AS c
    INNER JOIN app.documents AS d ON d.id = c.document_id
    INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
    WHERE c.deleted_at IS NULL
      AND d.deleted_at IS NULL
      AND dv.deleted_at IS NULL
      AND d.current_version_id IS NOT DISTINCT FROM c.version_id
      AND c.is_search_representative
      AND dv.status IN (
        'hybrid_ready'::app.document_status,
        'graph_pending'::app.document_status,
        'graph_ready'::app.document_status,
        'graph_ineligible'::app.document_status
      )
      AND (p_language IS NULL OR dv.language IS NOT DISTINCT FROM p_language)
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ),
  exact_terms AS (
    SELECT
      r.chunk_id,
      r.document_id,
      r.version_id,
      'exact'::text AS match_kind,
      1.0::double precision AS similarity
    FROM retrievable AS r
    INNER JOIN app.document_search_terms AS t ON t.chunk_id = r.chunk_id
    WHERE t.term_normalized = p_query_normalized
  ),
  alias_terms AS (
    SELECT
      r.chunk_id,
      r.document_id,
      r.version_id,
      'alias'::text AS match_kind,
      1.0::double precision AS similarity
    FROM retrievable AS r
    INNER JOIN app.document_search_terms AS t ON t.chunk_id = r.chunk_id
    INNER JOIN app.search_aliases AS sa
      ON t.term_normalized = search.normalize_arabic_v1(sa.canonical_term)
    WHERE sa.alias_normalized = p_query_normalized
  ),
  trigram_terms AS (
    SELECT
      r.chunk_id,
      r.document_id,
      r.version_id,
      'trigram'::text AS match_kind,
      similarity(t.term_normalized, p_query_normalized)::double precision AS similarity
    FROM retrievable AS r
    INNER JOIN app.document_search_terms AS t ON t.chunk_id = r.chunk_id
    WHERE t.term_normalized % p_query_normalized
      AND t.term_normalized IS DISTINCT FROM p_query_normalized
  ),
  ranked AS (
    SELECT
      combined.chunk_id,
      combined.document_id,
      combined.version_id,
      combined.match_kind,
      combined.similarity,
      ROW_NUMBER() OVER (
        PARTITION BY combined.chunk_id
        ORDER BY
          CASE combined.match_kind
            WHEN 'exact' THEN 0
            WHEN 'alias' THEN 1
            ELSE 2
          END,
          combined.similarity DESC,
          combined.chunk_id ASC
      ) AS keep_row
    FROM (
      SELECT * FROM exact_terms
      UNION ALL
      SELECT * FROM alias_terms
      UNION ALL
      SELECT * FROM trigram_terms
    ) AS combined
  )
  SELECT
    ranked.chunk_id,
    ranked.document_id,
    ranked.version_id,
    ranked.match_kind,
    ranked.similarity
  FROM ranked
  WHERE ranked.keep_row = 1
  ORDER BY
    CASE ranked.match_kind
      WHEN 'exact' THEN 0
      WHEN 'alias' THEN 1
      ELSE 2
    END,
    ranked.similarity DESC,
    ranked.chunk_id ASC
  LIMIT capped_limit;
END;
$fn$;

COMMENT ON FUNCTION app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text
) IS
  'Security-invoker exact/alias/trigram term candidates. Empty terms yield zero rows.';

CREATE OR REPLACE FUNCTION app.recheck_retrieval_candidates(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_chunk_ids uuid[]
)
RETURNS TABLE (
  chunk_id uuid,
  document_id uuid,
  version_id uuid
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

  IF cardinality(p_chunk_ids) > 300 THEN
    RAISE EXCEPTION 'recheck_batch_exceeds_limit';
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
    c.version_id
  FROM requested AS req
  INNER JOIN app.document_chunks AS c ON c.id = req.chunk_id
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND c.is_search_representative
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

COMMENT ON FUNCTION app.recheck_retrieval_candidates(uuid, text, bigint, uuid[]) IS
  'Authoritative current-version/ACL recheck. Drops stale, deleted, and unauthorized IDs.';

REVOKE ALL ON FUNCTION app.retrieval_exact_row_cap() FROM PUBLIC;
REVOKE ALL ON FUNCTION app.count_authorized_retrievable_chunks(uuid, text, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.retrieve_dense_candidates(
  uuid, text, bigint, extensions.vector, text, text, integer, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.recheck_retrieval_candidates(uuid, text, bigint, uuid[]) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.retrieval_exact_row_cap() TO app_api;
GRANT EXECUTE ON FUNCTION app.count_authorized_retrievable_chunks(uuid, text, bigint, text) TO app_api;
GRANT EXECUTE ON FUNCTION app.retrieve_dense_candidates(
  uuid, text, bigint, extensions.vector, text, text, integer, text
) TO app_api;
GRANT EXECUTE ON FUNCTION app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text
) TO app_api;
GRANT EXECUTE ON FUNCTION app.recheck_retrieval_candidates(uuid, text, bigint, uuid[]) TO app_api;
