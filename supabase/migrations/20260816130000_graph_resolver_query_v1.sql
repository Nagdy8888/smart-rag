-- Phase 5 Packet 5: query-time resolver grants, inspection RPC, repair enqueue,
-- visibility counts, and a recorded survival-sample window.
-- Expand-only. Do not DROP columns or tables.

GRANT SELECT ON app.lightrag_source_map TO app_api;
GRANT SELECT ON app.lightrag_chunk_map TO app_api;
GRANT SELECT ON app.graph_evidence_map TO app_api;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'lightrag_source_map'
      AND policyname = 'lightrag_source_map_api_select'
  ) THEN
    CREATE POLICY lightrag_source_map_api_select
      ON app.lightrag_source_map
      FOR SELECT
      TO app_api
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'lightrag_chunk_map'
      AND policyname = 'lightrag_chunk_map_api_select'
  ) THEN
    CREATE POLICY lightrag_chunk_map_api_select
      ON app.lightrag_chunk_map
      FOR SELECT
      TO app_api
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_evidence_map'
      AND policyname = 'graph_evidence_map_api_select'
  ) THEN
    CREATE POLICY graph_evidence_map_api_select
      ON app.graph_evidence_map
      FOR SELECT
      TO app_api
      USING (true);
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS app.graph_survival_samples (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  recorded_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  survival_ratio numeric(5, 4) NOT NULL,
  query_mode text NOT NULL,
  CONSTRAINT graph_survival_samples_ratio_range CHECK (
    survival_ratio >= 0 AND survival_ratio <= 1
  ),
  CONSTRAINT graph_survival_samples_mode_nonempty CHECK (btrim(query_mode) <> '')
);

COMMENT ON TABLE app.graph_survival_samples IS
  'Rolling graph_survival_ratio samples. Alert interface is mean of the latest 20 Combined queries; Packet 5 records the window only.';

ALTER TABLE app.graph_survival_samples ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_survival_samples FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_survival_samples'
      AND policyname = 'graph_survival_samples_api_rw'
  ) THEN
    CREATE POLICY graph_survival_samples_api_rw
      ON app.graph_survival_samples
      FOR ALL
      TO app_api
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_survival_samples'
      AND policyname = 'graph_survival_samples_worker_rw'
  ) THEN
    CREATE POLICY graph_survival_samples_worker_rw
      ON app.graph_survival_samples
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;
END
$$;

GRANT SELECT, INSERT, DELETE ON app.graph_survival_samples TO app_api;
GRANT SELECT, INSERT, DELETE ON app.graph_survival_samples TO app_worker;
REVOKE ALL ON app.graph_survival_samples FROM PUBLIC;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_map_repair_jobs'
      AND policyname = 'graph_map_repair_jobs_api_rw'
  ) THEN
    CREATE POLICY graph_map_repair_jobs_api_rw
      ON app.graph_map_repair_jobs
      FOR ALL
      TO app_api
      USING (true)
      WITH CHECK (true);
  END IF;
END
$$;

GRANT SELECT, INSERT, UPDATE ON app.graph_map_repair_jobs TO app_api;

CREATE OR REPLACE FUNCTION app.enqueue_graph_map_repair(
  p_workspace_key text,
  p_document_id uuid,
  p_version_id uuid,
  p_object_type text,
  p_object_id text,
  p_map_kind text,
  p_config_generation text,
  p_reason text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  repair_id uuid;
BEGIN
  IF p_workspace_key IS NULL OR btrim(p_workspace_key) = ''
     OR p_object_type IS NULL OR btrim(p_object_type) = ''
     OR p_object_id IS NULL OR btrim(p_object_id) = ''
     OR p_map_kind IS NULL OR btrim(p_map_kind) = ''
     OR p_config_generation IS NULL OR btrim(p_config_generation) = ''
     OR p_reason IS NULL OR btrim(p_reason) = '' THEN
    RAISE EXCEPTION 'graph_repair_keys_required';
  END IF;

  INSERT INTO app.graph_map_repair_jobs (
    workspace_key, document_id, version_id, graph_object_type,
    graph_object_id, map_kind, config_generation, reason
  )
  VALUES (
    btrim(p_workspace_key),
    p_document_id,
    p_version_id,
    btrim(p_object_type),
    left(btrim(p_object_id), 512),
    btrim(p_map_kind),
    btrim(p_config_generation),
    left(btrim(p_reason), 512)
  )
  ON CONFLICT (
    workspace_key, graph_object_type, graph_object_id,
    map_kind, config_generation
  ) DO UPDATE SET
    reason = EXCLUDED.reason,
    status = 'pending'::app.job_status,
    updated_at = timezone('utc', now())
  RETURNING id INTO repair_id;

  RETURN repair_id;
END;
$fn$;

COMMENT ON FUNCTION app.enqueue_graph_map_repair(
  text, uuid, uuid, text, text, text, text, text
) IS
  'Bounded query-time mapping repair upsert as app_api. Never runs Hybrid. No corpus text.';

CREATE OR REPLACE FUNCTION app.graph_visibility_counts(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_relevant_version_ids uuid[] DEFAULT NULL
)
RETURNS TABLE (
  partial_readiness_count integer,
  acl_blindness_count integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN QUERY SELECT 0, 0;
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    (
      SELECT count(*)::integer
      FROM app.document_versions AS dv
      JOIN app.documents AS d ON d.id = dv.document_id
      WHERE d.deleted_at IS NULL
        AND dv.deleted_at IS NULL
        AND d.current_version_id IS NOT DISTINCT FROM dv.id
        AND d.visibility = 'company_visible'::app.document_visibility
        AND dv.status IN (
          'hybrid_ready'::app.document_status,
          'graph_pending'::app.document_status
        )
        AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
        AND (
          p_relevant_version_ids IS NULL
          OR dv.id = ANY (p_relevant_version_ids)
        )
    ) AS partial_readiness_count,
    (
      SELECT count(*)::integer
      FROM app.document_versions AS dv
      JOIN app.documents AS d ON d.id = dv.document_id
      WHERE d.deleted_at IS NULL
        AND dv.deleted_at IS NULL
        AND d.current_version_id IS NOT DISTINCT FROM dv.id
        AND d.visibility = 'restricted'::app.document_visibility
        AND (
          dv.status = 'graph_ineligible'::app.document_status
          OR d.graph_eligible IS NOT TRUE
          OR dv.graph_eligible IS NOT TRUE
        )
        AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
        AND (
          p_relevant_version_ids IS NULL
          OR dv.id = ANY (p_relevant_version_ids)
        )
    ) AS acl_blindness_count;
END;
$fn$;

COMMENT ON FUNCTION app.graph_visibility_counts(uuid, text, bigint, uuid[]) IS
  'Authorized company-visible partial-readiness and authorized-only ACL-blindness counts. Unauthorized restricted documents are omitted.';

CREATE OR REPLACE FUNCTION app.inspect_graph_neighborhood(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_workspace_key text,
  p_config_generation text,
  p_entity_keys text[],
  p_document_id uuid,
  p_depth integer,
  p_row_limit integer
)
RETURNS TABLE (
  object_type text,
  object_id text,
  chunk_id uuid,
  document_id uuid,
  version_id uuid,
  support numeric,
  hop integer
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  capped_depth integer;
  capped_rows integer;
BEGIN
  PERFORM set_config('statement_timeout', '3s', true);

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  IF (p_entity_keys IS NULL OR cardinality(p_entity_keys) = 0)
     AND p_document_id IS NULL THEN
    RETURN;
  END IF;

  IF p_entity_keys IS NOT NULL AND cardinality(p_entity_keys) > 12 THEN
    RAISE EXCEPTION 'inspect_seed_exceeds_limit';
  END IF;

  capped_depth := GREATEST(1, LEAST(COALESCE(p_depth, 3), 3));
  capped_rows := GREATEST(1, LEAST(COALESCE(p_row_limit, 200), 200));

  RETURN QUERY
  WITH RECURSIVE authorized_maps AS (
    SELECT
      gem.graph_object_type,
      gem.graph_object_id,
      gem.chunk_id,
      gem.support,
      gem.version_id,
      c.document_id,
      gem.provenance
    FROM app.graph_evidence_map AS gem
    INNER JOIN app.document_chunks AS c ON c.id = gem.chunk_id
    INNER JOIN app.documents AS d ON d.id = c.document_id
    INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
    WHERE gem.workspace_key = p_workspace_key
      AND gem.config_generation = p_config_generation
      AND gem.support >= 0.80
      AND gem.pipeline_version = 'graph_pipeline_v1'
      AND c.deleted_at IS NULL
      AND d.deleted_at IS NULL
      AND dv.deleted_at IS NULL
      AND d.current_version_id IS NOT DISTINCT FROM c.version_id
      AND dv.status = 'graph_ready'::app.document_status
      AND d.graph_eligible IS TRUE
      AND dv.graph_eligible IS TRUE
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ),
  seed AS (
    SELECT
      authorized_maps.graph_object_type,
      authorized_maps.graph_object_id,
      authorized_maps.chunk_id,
      authorized_maps.support,
      authorized_maps.version_id,
      authorized_maps.document_id,
      authorized_maps.provenance,
      0 AS hop
    FROM authorized_maps
    WHERE (
      p_entity_keys IS NOT NULL
      AND cardinality(p_entity_keys) > 0
      AND authorized_maps.graph_object_type = 'entity'
      AND authorized_maps.graph_object_id = ANY (p_entity_keys)
    )
    OR (
      p_document_id IS NOT NULL
      AND authorized_maps.document_id = p_document_id
    )
  ),
  walk AS (
    SELECT seed.* FROM seed
    UNION
    SELECT
      nxt.graph_object_type,
      nxt.graph_object_id,
      nxt.chunk_id,
      nxt.support,
      nxt.version_id,
      nxt.document_id,
      nxt.provenance,
      walk.hop + 1
    FROM walk
    INNER JOIN authorized_maps AS nxt ON (
      (
        walk.graph_object_type = 'entity'
        AND nxt.graph_object_type = 'statement'
        AND (
          nxt.provenance ->> 'src' = walk.provenance ->> 'vendor_name'
          OR nxt.provenance ->> 'tgt' = walk.provenance ->> 'vendor_name'
        )
      )
      OR (
        walk.graph_object_type = 'statement'
        AND nxt.graph_object_type = 'entity'
        AND (
          walk.provenance ->> 'src' = nxt.provenance ->> 'vendor_name'
          OR walk.provenance ->> 'tgt' = nxt.provenance ->> 'vendor_name'
        )
      )
      OR (
        walk.graph_object_type = 'statement'
        AND nxt.graph_object_type = 'path_edge'
        AND nxt.provenance ->> 'statement_id' = walk.graph_object_id
      )
      OR (
        walk.graph_object_type = 'path_edge'
        AND nxt.graph_object_type = 'statement'
        AND walk.provenance ->> 'statement_id' = nxt.graph_object_id
      )
    )
    WHERE walk.hop < capped_depth
  )
  SELECT
    ranked.graph_object_type,
    ranked.graph_object_id,
    ranked.chunk_id,
    ranked.document_id,
    ranked.version_id,
    ranked.support,
    ranked.hop
  FROM (
    SELECT DISTINCT ON (
      walk.graph_object_type,
      walk.graph_object_id,
      walk.chunk_id
    )
      walk.graph_object_type,
      walk.graph_object_id,
      walk.chunk_id,
      walk.document_id,
      walk.version_id,
      walk.support,
      walk.hop
    FROM walk
    ORDER BY
      walk.graph_object_type,
      walk.graph_object_id,
      walk.chunk_id,
      walk.hop ASC
  ) AS ranked
  ORDER BY ranked.hop ASC, ranked.graph_object_id ASC, ranked.chunk_id ASC
  LIMIT capped_rows;
END;
$fn$;

COMMENT ON FUNCTION app.inspect_graph_neighborhood(
  uuid, text, bigint, text, text, text[], uuid, integer, integer
) IS
  'SQL-level graph inspection: depth 3, 200 rows, 3s statement_timeout. No vendor prose.';

REVOKE ALL ON FUNCTION app.enqueue_graph_map_repair(
  text, uuid, uuid, text, text, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.graph_visibility_counts(uuid, text, bigint, uuid[])
  FROM PUBLIC;
REVOKE ALL ON FUNCTION app.inspect_graph_neighborhood(
  uuid, text, bigint, text, text, text[], uuid, integer, integer
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.enqueue_graph_map_repair(
  text, uuid, uuid, text, text, text, text, text
) TO app_api;
GRANT EXECUTE ON FUNCTION app.enqueue_graph_map_repair(
  text, uuid, uuid, text, text, text, text, text
) TO app_worker;
GRANT EXECUTE ON FUNCTION app.graph_visibility_counts(uuid, text, bigint, uuid[])
  TO app_api;
GRANT EXECUTE ON FUNCTION app.inspect_graph_neighborhood(
  uuid, text, bigint, text, text, text[], uuid, integer, integer
) TO app_api;
