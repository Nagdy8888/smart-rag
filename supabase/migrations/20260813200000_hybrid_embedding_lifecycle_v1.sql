-- Phase 3 Packet 7: embedding ledger, canonical/Hybrid lifecycle, graph handoff RPCs.

ALTER TABLE app.document_versions
  ADD COLUMN IF NOT EXISTS is_current boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS chunk_set_hash text,
  ADD COLUMN IF NOT EXISTS embedding_model text,
  ADD COLUMN IF NOT EXISTS embedding_policy_hash text,
  ADD COLUMN IF NOT EXISTS hybrid_verified_at timestamptz,
  ADD COLUMN IF NOT EXISTS bm25_verified_at timestamptz,
  ADD COLUMN IF NOT EXISTS retrieval_eligible boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS graph_handoff_at timestamptz;

ALTER TABLE app.document_chunks
  ADD COLUMN IF NOT EXISTS contextual_text text,
  ADD COLUMN IF NOT EXISTS content_hash text,
  ADD COLUMN IF NOT EXISTS duplicate_of_chunk_id uuid REFERENCES app.document_chunks (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS is_search_representative boolean NOT NULL DEFAULT true;

CREATE TABLE IF NOT EXISTS app.embedding_operation_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  operation_key text NOT NULL,
  policy_hash text NOT NULL,
  model text NOT NULL,
  dimensions integer NOT NULL,
  input_count integer NOT NULL DEFAULT 0,
  status text NOT NULL DEFAULT 'pending',
  provider_request_id text,
  reserved_usd numeric(12, 6),
  actual_usd numeric(12, 6),
  attempt_count integer NOT NULL DEFAULT 0,
  result_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT embedding_operation_ledger_operation_uq UNIQUE (version_id, operation_key),
  CONSTRAINT embedding_operation_ledger_status_check CHECK (
    status IN ('pending', 'completed', 'failed')
  )
);

CREATE TRIGGER embedding_operation_ledger_touch_updated_at
  BEFORE UPDATE ON app.embedding_operation_ledger
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

COMMENT ON TABLE app.embedding_operation_ledger IS
  'Durable embedding batch ledger keyed by version/policy hash. Not exactly-once billing.';

INSERT INTO app.bm25_index_versions (
  version_number,
  normalization_version,
  index_schema_version,
  is_active,
  activated_at
)
SELECT 1, search.arabic_normalization_version(), 'bm25_v1', true, timezone('utc', now())
WHERE NOT EXISTS (SELECT 1 FROM app.bm25_index_versions WHERE is_active = true);

CREATE OR REPLACE FUNCTION app.record_embedding_ledger(
  p_version_id uuid,
  p_operation_key text,
  p_policy_hash text,
  p_model text,
  p_dimensions integer,
  p_input_count integer,
  p_status text,
  p_provider_request_id text DEFAULT NULL,
  p_reserved_usd numeric DEFAULT NULL,
  p_actual_usd numeric DEFAULT NULL,
  p_result_ref jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  ledger_id uuid;
BEGIN
  INSERT INTO app.embedding_operation_ledger (
    version_id,
    operation_key,
    policy_hash,
    model,
    dimensions,
    input_count,
    status,
    provider_request_id,
    reserved_usd,
    actual_usd,
    result_ref,
    attempt_count
  )
  VALUES (
    p_version_id,
    p_operation_key,
    p_policy_hash,
    p_model,
    p_dimensions,
    p_input_count,
    p_status,
    p_provider_request_id,
    p_reserved_usd,
    p_actual_usd,
    COALESCE(p_result_ref, '{}'::jsonb),
    1
  )
  ON CONFLICT (version_id, operation_key) DO UPDATE
  SET
    status = EXCLUDED.status,
    provider_request_id = COALESCE(EXCLUDED.provider_request_id, app.embedding_operation_ledger.provider_request_id),
    reserved_usd = COALESCE(EXCLUDED.reserved_usd, app.embedding_operation_ledger.reserved_usd),
    actual_usd = COALESCE(EXCLUDED.actual_usd, app.embedding_operation_ledger.actual_usd),
    result_ref = app.embedding_operation_ledger.result_ref || EXCLUDED.result_ref,
    attempt_count = app.embedding_operation_ledger.attempt_count + 1,
    updated_at = timezone('utc', now())
  RETURNING id INTO ledger_id;

  RETURN ledger_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.enqueue_bm25_projection_for_version(
  p_version_id uuid,
  p_chunk_set_hash text,
  p_operation_key text DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  active_norm text;
  active_schema text;
  job_id uuid;
  idem text;
BEGIN
  SELECT normalization_version, index_schema_version
  INTO active_norm, active_schema
  FROM app.bm25_index_versions
  WHERE is_active = true
  ORDER BY version_number DESC
  LIMIT 1;

  idem := COALESCE(
    p_operation_key,
    format(
      'bm25:upsert:%s:%s:%s:%s',
      p_version_id,
      p_chunk_set_hash,
      active_norm,
      active_schema
    )
  );

  INSERT INTO app.bm25_index_jobs (
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    p_version_id,
    'upsert'::app.bm25_job_operation,
    'normal'::app.job_priority,
    idem,
    jsonb_build_object(
      'version_id', p_version_id,
      'chunk_set_hash', p_chunk_set_hash,
      'normalization_version', active_norm,
      'index_schema_version', active_schema
    )
  )
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id INTO job_id;

  IF job_id IS NULL THEN
    SELECT j.id INTO job_id
    FROM app.bm25_index_jobs AS j
    WHERE j.idempotency_key = idem;
  END IF;

  RETURN job_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.finalize_hybrid_ready(
  p_version_id uuid,
  p_chunk_set_hash text,
  p_bm25_job_id uuid DEFAULT NULL
)
RETURNS app.document_versions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_row app.document_versions%ROWTYPE;
  doc app.documents%ROWTYPE;
BEGIN
  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'version not found';
  END IF;

  IF version_row.chunk_set_hash IS DISTINCT FROM p_chunk_set_hash THEN
    RAISE EXCEPTION 'chunk_set_hash mismatch';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = version_row.document_id
  FOR UPDATE;

  UPDATE app.document_versions AS dv
  SET
    status = 'hybrid_ready'::app.document_status,
    hybrid_verified_at = timezone('utc', now()),
    bm25_verified_at = timezone('utc', now()),
    updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id
  RETURNING * INTO version_row;

  IF doc.graph_eligible
    AND doc.visibility = 'company_visible'::app.document_visibility
    AND doc.deleted_at IS NULL
    AND version_row.graph_eligible THEN
    PERFORM app.enqueue_graph_pending_handoff(p_version_id);
  ELSE
    UPDATE app.document_versions AS dv
    SET status = 'graph_ineligible'::app.document_status,
        updated_at = timezone('utc', now())
    WHERE dv.id = p_version_id
      AND dv.status = 'hybrid_ready'::app.document_status
    RETURNING * INTO version_row;
  END IF;

  RETURN version_row;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.enqueue_graph_pending_handoff(
  p_version_id uuid,
  p_content_hash text DEFAULT NULL,
  p_lightrag_version text DEFAULT 'lightrag_v1',
  p_pipeline_version text DEFAULT 'graph_pipeline_v1'
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_row app.document_versions%ROWTYPE;
  doc app.documents%ROWTYPE;
  job_id uuid;
  content_hash text;
  idem text;
BEGIN
  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'version not found';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = version_row.document_id;

  IF NOT doc.graph_eligible OR NOT version_row.graph_eligible THEN
    UPDATE app.document_versions AS dv
    SET status = 'graph_ineligible'::app.document_status,
        updated_at = timezone('utc', now())
    WHERE dv.id = p_version_id;
    RETURN NULL;
  END IF;

  content_hash := COALESCE(p_content_hash, version_row.content_hash, version_row.chunk_set_hash);
  idem := format(
    'graph_index:%s:%s:%s:%s',
    p_version_id,
    content_hash,
    p_lightrag_version,
    p_pipeline_version
  );

  INSERT INTO app.lightrag_index_jobs (
    document_id,
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    version_row.document_id,
    p_version_id,
    'index'::app.lightrag_job_operation,
    'normal'::app.job_priority,
    idem,
    jsonb_build_object(
      'document_id', version_row.document_id,
      'version_id', p_version_id,
      'content_hash', content_hash,
      'lightrag_version', p_lightrag_version,
      'graph_pipeline_version', p_pipeline_version,
      'chunk_set_hash', version_row.chunk_set_hash
    )
  )
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id INTO job_id;

  IF job_id IS NULL THEN
    SELECT j.id INTO job_id
    FROM app.lightrag_index_jobs AS j
    WHERE j.idempotency_key = idem;
  END IF;

  UPDATE app.document_versions AS dv
  SET
    status = 'graph_pending'::app.document_status,
    graph_handoff_at = timezone('utc', now()),
    updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id;

  RETURN job_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.activate_graph_ineligible_version(
  p_version_id uuid
)
RETURNS app.documents
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_row app.document_versions%ROWTYPE;
  doc app.documents%ROWTYPE;
BEGIN
  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'version not found';
  END IF;

  IF version_row.status <> 'hybrid_ready'::app.document_status THEN
    RAISE EXCEPTION 'version must be hybrid_ready before activation';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = version_row.document_id
  FOR UPDATE;

  IF doc.graph_eligible OR version_row.graph_eligible THEN
    RAISE EXCEPTION 'graph-eligible versions require Phase 5 switch';
  END IF;

  UPDATE app.document_versions AS dv
  SET is_current = false, updated_at = timezone('utc', now())
  WHERE dv.document_id = doc.id AND dv.is_current = true;

  UPDATE app.document_versions AS dv
  SET is_current = true, updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id;

  UPDATE app.documents AS d
  SET current_version_id = p_version_id, updated_at = timezone('utc', now())
  WHERE d.id = doc.id
  RETURNING * INTO doc;

  RETURN doc;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.exclude_version_from_retrieval(
  p_version_id uuid,
  p_reason text DEFAULT 'deletion_or_acl'
)
RETURNS app.document_versions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_row app.document_versions%ROWTYPE;
  doc app.documents%ROWTYPE;
BEGIN
  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'version not found';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = version_row.document_id
  FOR UPDATE;

  UPDATE app.document_versions AS dv
  SET
    retrieval_eligible = false,
    deleted_at = COALESCE(dv.deleted_at, timezone('utc', now())),
    status = 'deletion_pending'::app.document_status,
    updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id
  RETURNING * INTO version_row;

  UPDATE app.document_chunks AS dc
  SET deleted_at = timezone('utc', now()), updated_at = timezone('utc', now())
  WHERE dc.version_id = p_version_id AND dc.deleted_at IS NULL;

  UPDATE app.documents AS d
  SET
    visibility_generation = d.visibility_generation + 1,
    graph_eligible = false,
    updated_at = timezone('utc', now())
  WHERE d.id = doc.id;

  UPDATE app.company_settings
  SET
    authorization_version = authorization_version + 1,
    visibility_generation = visibility_generation + 1,
    updated_at = timezone('utc', now())
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;

  INSERT INTO app.bm25_index_jobs (
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    p_version_id,
    'delete'::app.bm25_job_operation,
    'high'::app.job_priority,
    format('delete:%s:%s', p_version_id, doc.visibility_generation),
    jsonb_build_object('version_id', p_version_id, 'reason', p_reason)
  )
  ON CONFLICT (idempotency_key) DO NOTHING;

  PERFORM app.emit_graph_acl_remove_for_document(doc.id);

  RETURN version_row;
END;
$fn$;

ALTER TABLE app.embedding_operation_ledger ENABLE ROW LEVEL SECURITY;

CREATE POLICY embedding_operation_ledger_worker_rw
  ON app.embedding_operation_ledger
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE ON app.embedding_operation_ledger TO app_worker;

REVOKE ALL ON FUNCTION app.record_embedding_ledger(uuid, text, text, text, integer, integer, text, text, numeric, numeric, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.enqueue_bm25_projection_for_version(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.finalize_hybrid_ready(uuid, text, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.enqueue_graph_pending_handoff(uuid, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.activate_graph_ineligible_version(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.exclude_version_from_retrieval(uuid, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.record_embedding_ledger(uuid, text, text, text, integer, integer, text, text, numeric, numeric, jsonb) TO app_worker;
GRANT EXECUTE ON FUNCTION app.enqueue_bm25_projection_for_version(uuid, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.finalize_hybrid_ready(uuid, text, uuid) TO app_worker;
GRANT EXECUTE ON FUNCTION app.enqueue_graph_pending_handoff(uuid, text, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.activate_graph_ineligible_version(uuid) TO app_worker;
GRANT EXECUTE ON FUNCTION app.exclude_version_from_retrieval(uuid, text) TO app_worker;
