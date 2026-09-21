-- Additive term-channel needles. Six-argument calls remain valid because
-- p_extra_terms defaults to NULL. ACL and current-version predicates are
-- unchanged. Extra terms are bound text values, never concatenated SQL.

DROP FUNCTION IF EXISTS app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text
);
DROP FUNCTION IF EXISTS app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text, text[]
);

CREATE FUNCTION app.retrieve_term_candidates(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_query_normalized text,
  p_candidate_limit integer,
  p_language text DEFAULT NULL,
  p_extra_terms text[] DEFAULT NULL
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
  WITH needles AS (
    SELECT DISTINCT search.normalize_arabic_v1(btrim(raw_term)) AS needle
    FROM unnest(
      ARRAY[p_query_normalized]
      || COALESCE(p_extra_terms[1:8], ARRAY[]::text[])
    ) AS raw_term
    WHERE btrim(COALESCE(raw_term, '')) <> ''
      AND position(chr(0) IN raw_term) = 0
      AND char_length(search.normalize_arabic_v1(btrim(raw_term)))
        BETWEEN 2 AND 256
  ),
  retrievable AS (
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
    INNER JOIN needles AS n ON t.term_normalized = n.needle
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
    INNER JOIN needles AS n ON sa.alias_normalized = n.needle
  ),
  trigram_terms AS (
    SELECT
      r.chunk_id,
      r.document_id,
      r.version_id,
      'trigram'::text AS match_kind,
      similarity(t.term_normalized, n.needle)::double precision AS similarity
    FROM retrievable AS r
    INNER JOIN app.document_search_terms AS t ON t.chunk_id = r.chunk_id
    INNER JOIN needles AS n
      ON t.term_normalized % n.needle
     AND t.term_normalized IS DISTINCT FROM n.needle
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
  uuid, text, bigint, text, integer, text, text[]
) IS
  'Security-invoker exact/alias/trigram term candidates. Extra needles are bound text. Empty terms yield zero rows.';

REVOKE ALL ON FUNCTION app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text, text[]
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.retrieve_term_candidates(
  uuid, text, bigint, text, integer, text, text[]
) TO app_api;
