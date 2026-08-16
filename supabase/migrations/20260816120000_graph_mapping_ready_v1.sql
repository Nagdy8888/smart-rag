-- Phase 5 Packet 4: expand canonical graph maps, repair jobs, and telemetry.
-- Expand-only. Do not DROP columns. Vendor PROCESSED is not Graph Ready.

ALTER TABLE app.lightrag_source_map
  ADD COLUMN IF NOT EXISTS version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS workspace_key text,
  ADD COLUMN IF NOT EXISTS pipeline_version text,
  ADD COLUMN IF NOT EXISTS config_generation text,
  ADD COLUMN IF NOT EXISTS source_content_hash text,
  ADD COLUMN IF NOT EXISTS language text,
  ADD COLUMN IF NOT EXISTS method text,
  ADD COLUMN IF NOT EXISTS score numeric(5, 4),
  ADD COLUMN IF NOT EXISTS support numeric(5, 4),
  ADD COLUMN IF NOT EXISTS source_hash text,
  ADD COLUMN IF NOT EXISTS target_hash text,
  ADD COLUMN IF NOT EXISTS source_span jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS target_span jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS provenance jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE app.lightrag_chunk_map
  ADD COLUMN IF NOT EXISTS version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS workspace_key text,
  ADD COLUMN IF NOT EXISTS pipeline_version text,
  ADD COLUMN IF NOT EXISTS config_generation text,
  ADD COLUMN IF NOT EXISTS language text,
  ADD COLUMN IF NOT EXISTS method text,
  ADD COLUMN IF NOT EXISTS score numeric(5, 4),
  ADD COLUMN IF NOT EXISTS support numeric(5, 4),
  ADD COLUMN IF NOT EXISTS source_hash text,
  ADD COLUMN IF NOT EXISTS target_hash text,
  ADD COLUMN IF NOT EXISTS source_span jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS target_span jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS provenance jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE app.graph_evidence_map
  ADD COLUMN IF NOT EXISTS version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  ADD COLUMN IF NOT EXISTS workspace_key text,
  ADD COLUMN IF NOT EXISTS pipeline_version text,
  ADD COLUMN IF NOT EXISTS config_generation text,
  ADD COLUMN IF NOT EXISTS language text,
  ADD COLUMN IF NOT EXISTS method text,
  ADD COLUMN IF NOT EXISTS score numeric(5, 4),
  ADD COLUMN IF NOT EXISTS support numeric(5, 4),
  ADD COLUMN IF NOT EXISTS source_hash text,
  ADD COLUMN IF NOT EXISTS target_hash text,
  ADD COLUMN IF NOT EXISTS source_span jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS target_span jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS provenance jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE UNIQUE INDEX IF NOT EXISTS lightrag_source_map_replay_uq
  ON app.lightrag_source_map (
    document_id,
    version_id,
    workspace_key,
    pipeline_version
  )
  WHERE version_id IS NOT NULL
    AND workspace_key IS NOT NULL
    AND pipeline_version IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS lightrag_chunk_map_replay_uq
  ON app.lightrag_chunk_map (
    workspace_key,
    version_id,
    lightrag_chunk_id,
    chunk_id
  )
  WHERE version_id IS NOT NULL
    AND workspace_key IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS graph_evidence_map_replay_uq
  ON app.graph_evidence_map (
    workspace_key,
    version_id,
    graph_object_type,
    graph_object_id,
    chunk_id,
    pipeline_version
  )
  WHERE version_id IS NOT NULL
    AND workspace_key IS NOT NULL
    AND pipeline_version IS NOT NULL;

COMMENT ON COLUMN app.lightrag_source_map.version_id IS
  'Canonical document_version_id used as LightRAG ids. Replay upserts this row.';
COMMENT ON COLUMN app.lightrag_source_map.config_generation IS
  'Workspace generation plus graph_pipeline_v1 chunker snapshot digest.';
COMMENT ON COLUMN app.lightrag_chunk_map.method IS
  'hash, span, overlap, or hybrid_support. Never vendor path or ordinal.';
COMMENT ON COLUMN app.graph_evidence_map.support IS
  'Accepted canonical passage support. Queryable rows are >= 0.80.';

CREATE TABLE IF NOT EXISTS app.graph_map_repair_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_key text NOT NULL,
  document_id uuid REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  graph_object_type text NOT NULL,
  graph_object_id text NOT NULL,
  map_kind text NOT NULL,
  config_generation text NOT NULL,
  reason text NOT NULL,
  payload_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  status app.job_status NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_map_repair_jobs_keys_nonempty CHECK (
    btrim(workspace_key) <> ''
    AND btrim(graph_object_type) <> ''
    AND btrim(graph_object_id) <> ''
    AND btrim(map_kind) <> ''
    AND btrim(config_generation) <> ''
    AND btrim(reason) <> ''
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS graph_map_repair_jobs_replay_uq
  ON app.graph_map_repair_jobs (
    workspace_key,
    graph_object_type,
    graph_object_id,
    map_kind,
    config_generation
  );

CREATE TRIGGER graph_map_repair_jobs_touch_updated_at
  BEFORE UPDATE ON app.graph_map_repair_jobs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

COMMENT ON TABLE app.graph_map_repair_jobs IS
  'Bounded mapping repair diagnostics. Repair never runs query-time Hybrid and cannot lower thresholds.';

CREATE TABLE IF NOT EXISTS app.graph_mapping_telemetry (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  workspace_key text NOT NULL,
  language text,
  object_type text NOT NULL,
  method text,
  truncation_count integer NOT NULL DEFAULT 0,
  failure_reason text,
  numerator integer NOT NULL DEFAULT 0,
  denominator integer NOT NULL DEFAULT 0,
  exclusion_count integer NOT NULL DEFAULT 0,
  pipeline_version text NOT NULL,
  config_generation text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_mapping_telemetry_counts_nonneg CHECK (
    truncation_count >= 0
    AND numerator >= 0
    AND denominator >= 0
    AND exclusion_count >= 0
  )
);

COMMENT ON TABLE app.graph_mapping_telemetry IS
  'Per-language mapping numerators, denominators, exclusions, method, and truncation.';

ALTER TABLE app.graph_map_repair_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_map_repair_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.graph_mapping_telemetry ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_mapping_telemetry FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'lightrag_source_map'
      AND policyname = 'lightrag_source_map_worker_rw'
  ) THEN
    CREATE POLICY lightrag_source_map_worker_rw
      ON app.lightrag_source_map
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'lightrag_chunk_map'
      AND policyname = 'lightrag_chunk_map_worker_rw'
  ) THEN
    CREATE POLICY lightrag_chunk_map_worker_rw
      ON app.lightrag_chunk_map
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_evidence_map'
      AND policyname = 'graph_evidence_map_worker_rw'
  ) THEN
    CREATE POLICY graph_evidence_map_worker_rw
      ON app.graph_evidence_map
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_entity_rules'
      AND policyname = 'graph_entity_rules_worker_rw'
  ) THEN
    CREATE POLICY graph_entity_rules_worker_rw
      ON app.graph_entity_rules
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_map_repair_jobs'
      AND policyname = 'graph_map_repair_jobs_worker_rw'
  ) THEN
    CREATE POLICY graph_map_repair_jobs_worker_rw
      ON app.graph_map_repair_jobs
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_mapping_telemetry'
      AND policyname = 'graph_mapping_telemetry_worker_rw'
  ) THEN
    CREATE POLICY graph_mapping_telemetry_worker_rw
      ON app.graph_mapping_telemetry
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;
END
$$;

GRANT SELECT, INSERT, UPDATE ON app.graph_map_repair_jobs TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.graph_mapping_telemetry TO app_worker;
GRANT DELETE ON app.lightrag_chunk_map TO app_worker;
GRANT DELETE ON app.graph_evidence_map TO app_worker;
REVOKE ALL ON app.graph_map_repair_jobs FROM PUBLIC;
REVOKE ALL ON app.graph_mapping_telemetry FROM PUBLIC;
