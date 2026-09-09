-- Additive dense v2: version/language filters inside count and ranking.

CREATE OR REPLACE FUNCTION app.count_authorized_retrievable_chunks_v2(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_language text DEFAULT NULL,
  p_version_id uuid DEFAULT NULL
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
    AND (p_version_id IS NULL OR c.version_id IS NOT DISTINCT FROM p_version_id)
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id);

  RETURN COALESCE(authorized_count, 0);
END;
$fn$;

COMMENT ON FUNCTION app.count_authorized_retrievable_chunks_v2(
  uuid, text, bigint, text, uuid
) IS
  'Authorized retrievable count with optional current-version filter inside SQL.';

CREATE OR REPLACE FUNCTION app.retrieve_dense_candidates_v2(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_query_embedding extensions.vector,
  p_profile text,
  p_mode text,
  p_candidate_limit integer,
  p_language text DEFAULT NULL,
  p_version_id uuid DEFAULT NULL
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
    authorized_count := app.count_authorized_retrievable_chunks_v2(
      caller_user_id,
      caller_role,
      caller_authorization_version,
      p_language,
      p_version_id
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
    AND (p_version_id IS NULL OR c.version_id IS NOT DISTINCT FROM p_version_id)
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ORDER BY c.embedding <=> p_query_embedding, c.id ASC
  LIMIT capped_limit;
END;
$fn$;

COMMENT ON FUNCTION app.retrieve_dense_candidates_v2(
  uuid, text, bigint, extensions.vector, text, text, integer, text, uuid
) IS
  'Dense ANN/exact with version and language filters inside count and ranking.';

REVOKE ALL ON FUNCTION app.count_authorized_retrievable_chunks_v2(
  uuid, text, bigint, text, uuid
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.retrieve_dense_candidates_v2(
  uuid, text, bigint, extensions.vector, text, text, integer, text, uuid
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.count_authorized_retrievable_chunks_v2(
  uuid, text, bigint, text, uuid
) TO app_api;
GRANT EXECUTE ON FUNCTION app.retrieve_dense_candidates_v2(
  uuid, text, bigint, extensions.vector, text, text, integer, text, uuid
) TO app_api;
