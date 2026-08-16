-- Phase 5 Packet 7: atomic pointer/version switch, cleanup tombstones, upgrade isolation.
-- Expand-only. Do not DROP TABLE or COLUMN. Pointer CAS is a short transaction.

ALTER TABLE app.lightrag_source_map
  ADD COLUMN IF NOT EXISTS retrieval_eligible boolean NOT NULL DEFAULT true;

ALTER TABLE app.lightrag_chunk_map
  ADD COLUMN IF NOT EXISTS retrieval_eligible boolean NOT NULL DEFAULT true;

ALTER TABLE app.graph_evidence_map
  ADD COLUMN IF NOT EXISTS retrieval_eligible boolean NOT NULL DEFAULT true;

COMMENT ON COLUMN app.lightrag_source_map.retrieval_eligible IS
  'False until Packet 7 switch or after deletion/ACL exclusion. Resolver drops ineligible rows.';
COMMENT ON COLUMN app.lightrag_chunk_map.retrieval_eligible IS
  'False for pending-switch maps and excluded versions. Immediate resolver authority.';
COMMENT ON COLUMN app.graph_evidence_map.retrieval_eligible IS
  'False for pending-switch maps and excluded versions. Immediate resolver authority.';

CREATE TABLE IF NOT EXISTS app.graph_cleanup_tombstones (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  workspace_key text NOT NULL,
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  recovery_phase text NOT NULL DEFAULT 'precheck',
  vendor_delete_status text,
  target_cleanup_at timestamptz NOT NULL,
  clean_rebuild_at timestamptz NOT NULL,
  verified_at timestamptz,
  rebuild_job_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_cleanup_tombstones_reason_known CHECK (
    reason IN ('deletion', 'acl_downgrade', 'version_supersede')
  ),
  CONSTRAINT graph_cleanup_tombstones_status_known CHECK (
    status IN ('pending', 'verified', 'failed', 'rebuild_scheduled', 'unfunded')
  ),
  CONSTRAINT graph_cleanup_tombstones_phase_known CHECK (
    recovery_phase IN (
      'precheck',
      'vendor_delete',
      'vendor_verify',
      'map_filter',
      'tombstone',
      'verified'
    )
  ),
  CONSTRAINT graph_cleanup_tombstones_keys_nonempty CHECK (
    btrim(workspace_key) <> ''
    AND btrim(reason) <> ''
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS graph_cleanup_tombstones_open_uq
  ON app.graph_cleanup_tombstones (version_id, workspace_key, reason)
  WHERE status IN ('pending', 'rebuild_scheduled', 'unfunded');

CREATE INDEX IF NOT EXISTS graph_cleanup_tombstones_sla_idx
  ON app.graph_cleanup_tombstones (target_cleanup_at, clean_rebuild_at, status);

COMMENT ON TABLE app.graph_cleanup_tombstones IS
  'Targeted graph delete/ACL cleanup SLA: 24h verify, 7-day clean rebuild. Retryable and filtered.';

CREATE TABLE IF NOT EXISTS app.graph_upgrade_qualifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  candidate_database text NOT NULL,
  candidate_schema text NOT NULL,
  runtime_database text NOT NULL,
  runtime_schema text NOT NULL,
  status text NOT NULL,
  consecutive_failures integer NOT NULL DEFAULT 0,
  embedding_model text NOT NULL DEFAULT 'text-embedding-3-large',
  embedding_dimensions integer NOT NULL DEFAULT 1024,
  notes text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_upgrade_status_known CHECK (
    status IN (
      'recorded',
      'refused_same_schema',
      'passed',
      'failed',
      'disable_review'
    )
  ),
  CONSTRAINT graph_upgrade_embedding_model_pin
    CHECK (embedding_model = 'text-embedding-3-large'),
  CONSTRAINT graph_upgrade_embedding_dimensions_pin
    CHECK (embedding_dimensions = 1024),
  CONSTRAINT graph_upgrade_keys_nonempty CHECK (
    btrim(candidate_database) <> ''
    AND btrim(candidate_schema) <> ''
    AND btrim(runtime_database) <> ''
    AND btrim(runtime_schema) <> ''
  )
);

COMMENT ON TABLE app.graph_upgrade_qualifications IS
  'LightRAG package/schema upgrade proof. A second workspace in runtime lightrag is not qualification.';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'graph_cleanup_tombstones_touch_updated_at'
  ) THEN
    CREATE TRIGGER graph_cleanup_tombstones_touch_updated_at
      BEFORE UPDATE ON app.graph_cleanup_tombstones
      FOR EACH ROW
      EXECUTE FUNCTION app.touch_updated_at();
  END IF;
END
$$;

ALTER TABLE app.graph_cleanup_tombstones ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_cleanup_tombstones FORCE ROW LEVEL SECURITY;
ALTER TABLE app.graph_upgrade_qualifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_upgrade_qualifications FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_cleanup_tombstones'
      AND policyname = 'graph_cleanup_tombstones_worker_rw'
  ) THEN
    CREATE POLICY graph_cleanup_tombstones_worker_rw
      ON app.graph_cleanup_tombstones
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_cleanup_tombstones'
      AND policyname = 'graph_cleanup_tombstones_api_select'
  ) THEN
    CREATE POLICY graph_cleanup_tombstones_api_select
      ON app.graph_cleanup_tombstones
      FOR SELECT
      TO app_api
      USING (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_upgrade_qualifications'
      AND policyname = 'graph_upgrade_qualifications_worker_rw'
  ) THEN
    CREATE POLICY graph_upgrade_qualifications_worker_rw
      ON app.graph_upgrade_qualifications
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_upgrade_qualifications'
      AND policyname = 'graph_upgrade_qualifications_api_select'
  ) THEN
    CREATE POLICY graph_upgrade_qualifications_api_select
      ON app.graph_upgrade_qualifications
      FOR SELECT
      TO app_api
      USING (true);
  END IF;
END
$$;

GRANT SELECT, INSERT, UPDATE ON app.graph_cleanup_tombstones TO app_worker;
GRANT SELECT ON app.graph_cleanup_tombstones TO app_api;
GRANT SELECT, INSERT, UPDATE ON app.graph_upgrade_qualifications TO app_worker;
GRANT SELECT ON app.graph_upgrade_qualifications TO app_api;

REVOKE ALL ON app.graph_cleanup_tombstones FROM PUBLIC, anon, authenticated, app_lightrag;
REVOKE ALL ON app.graph_upgrade_qualifications FROM PUBLIC, anon, authenticated, app_lightrag;

CREATE OR REPLACE FUNCTION app.assert_graph_build_index_allowed(
  p_document_id uuid,
  p_version_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc app.documents%ROWTYPE;
  version_row app.document_versions%ROWTYPE;
BEGIN
  IF p_document_id IS NULL OR p_version_id IS NULL THEN
    RAISE EXCEPTION 'graph build index rejected: missing ids';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = p_document_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'graph build index rejected: document not found';
  END IF;

  IF doc.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'graph build index rejected: document deleted';
  END IF;

  IF doc.visibility = 'restricted'::app.document_visibility THEN
    RAISE EXCEPTION 'graph build index rejected: restricted visibility';
  END IF;

  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id;

  IF NOT FOUND OR version_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'graph build index rejected: version missing or deleted';
  END IF;

  IF version_row.document_id IS DISTINCT FROM doc.id THEN
    RAISE EXCEPTION 'graph build index rejected: version/document mismatch';
  END IF;

  IF NOT version_row.graph_eligible THEN
    RAISE EXCEPTION 'graph build index rejected: version not graph_eligible';
  END IF;

  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION app.assert_graph_build_index_allowed(uuid, uuid) IS
  'Allow indexing a non-current graph-eligible version into a build workspace. Restricted/deleted fail closed. Live query still uses current_version_id.';

CREATE OR REPLACE FUNCTION app.reject_restricted_graph_index_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc_current uuid;
BEGIN
  IF COALESCE(NEW.payload_ref->>'reconciliation', '') = 'true' THEN
    RETURN NEW;
  END IF;
  IF NEW.operation = 'rebuild'::app.lightrag_job_operation
    AND NEW.document_id IS NULL
    AND (
      COALESCE(NEW.payload_ref->>'isolate_only', '') = 'true'
      OR COALESCE(NEW.payload_ref->>'verified_switch', '') = 'true'
    )
  THEN
    RETURN NEW;
  END IF;
  IF NEW.operation = 'index'::app.lightrag_job_operation
    AND NEW.document_id IS NOT NULL
    AND NEW.version_id IS NOT NULL
  THEN
    SELECT d.current_version_id
    INTO doc_current
    FROM app.documents AS d
    WHERE d.id = NEW.document_id;
    IF doc_current IS DISTINCT FROM NEW.version_id THEN
      PERFORM app.assert_graph_build_index_allowed(NEW.document_id, NEW.version_id);
      RETURN NEW;
    END IF;
  END IF;
  IF NEW.operation IN ('index', 'rebuild') THEN
    PERFORM app.assert_graph_index_allowed(NEW.document_id, NEW.version_id);
  END IF;
  RETURN NEW;
END;
$fn$;

COMMENT ON FUNCTION app.reject_restricted_graph_index_job() IS
  'Reject restricted graph index/rebuild jobs. Pending-switch non-current versions use the build gate. ACL expansion never auto-inserts index jobs.';

CREATE OR REPLACE FUNCTION app.mark_graph_maps_ineligible_for_version(
  p_version_id uuid
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_count integer := 0;
BEGIN
  UPDATE app.lightrag_source_map
  SET retrieval_eligible = false
  WHERE version_id = p_version_id
    AND retrieval_eligible IS TRUE;
  GET DIAGNOSTICS v_count = ROW_COUNT;

  UPDATE app.lightrag_chunk_map
  SET retrieval_eligible = false
  WHERE version_id = p_version_id
    AND retrieval_eligible IS TRUE;

  UPDATE app.graph_evidence_map
  SET retrieval_eligible = false
  WHERE version_id = p_version_id
    AND retrieval_eligible IS TRUE;

  RETURN v_count;
END;
$fn$;

COMMENT ON FUNCTION app.mark_graph_maps_ineligible_for_version(uuid) IS
  'Filter source/chunk/evidence maps for one version. Leaves rows retryable; never vendor graph surgery.';

CREATE OR REPLACE FUNCTION app.graph_maps_ineligible_on_version_exclusion()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'UPDATE'
    AND NEW.retrieval_eligible IS FALSE
    AND OLD.retrieval_eligible IS DISTINCT FROM FALSE
  THEN
    PERFORM app.mark_graph_maps_ineligible_for_version(NEW.id);
  END IF;
  IF TG_OP = 'UPDATE'
    AND NEW.deleted_at IS NOT NULL
    AND OLD.deleted_at IS NULL
  THEN
    PERFORM app.mark_graph_maps_ineligible_for_version(NEW.id);
  END IF;
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS graph_maps_ineligible_on_version_exclusion ON app.document_versions;
CREATE TRIGGER graph_maps_ineligible_on_version_exclusion
  AFTER UPDATE OF retrieval_eligible, deleted_at ON app.document_versions
  FOR EACH ROW
  EXECUTE FUNCTION app.graph_maps_ineligible_on_version_exclusion();

CREATE OR REPLACE FUNCTION app.graph_maps_ineligible_on_document_exclusion()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'UPDATE'
    AND (
      (OLD.graph_eligible IS TRUE AND NEW.graph_eligible IS FALSE)
      OR (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
    )
    AND NEW.current_version_id IS NOT NULL
  THEN
    PERFORM app.mark_graph_maps_ineligible_for_version(NEW.current_version_id);
  END IF;
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS graph_maps_ineligible_on_document_exclusion ON app.documents;
CREATE TRIGGER graph_maps_ineligible_on_document_exclusion
  AFTER UPDATE OF graph_eligible, deleted_at ON app.documents
  FOR EACH ROW
  EXECUTE FUNCTION app.graph_maps_ineligible_on_document_exclusion();

CREATE OR REPLACE FUNCTION app.upsert_graph_cleanup_tombstone(
  p_document_id uuid,
  p_version_id uuid,
  p_workspace_key text,
  p_reason text,
  p_recovery_phase text DEFAULT 'precheck',
  p_vendor_delete_status text DEFAULT NULL,
  p_status text DEFAULT 'pending',
  p_payload jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_id uuid;
  v_now timestamptz := timezone('utc', now());
BEGIN
  INSERT INTO app.graph_cleanup_tombstones (
    document_id,
    version_id,
    workspace_key,
    reason,
    status,
    recovery_phase,
    vendor_delete_status,
    target_cleanup_at,
    clean_rebuild_at,
    payload
  )
  VALUES (
    p_document_id,
    p_version_id,
    p_workspace_key,
    p_reason,
    COALESCE(p_status, 'pending'),
    COALESCE(p_recovery_phase, 'precheck'),
    p_vendor_delete_status,
    v_now + interval '24 hours',
    v_now + interval '7 days',
    COALESCE(p_payload, '{}'::jsonb)
  )
  ON CONFLICT (version_id, workspace_key, reason)
    WHERE status IN ('pending', 'rebuild_scheduled', 'unfunded')
  DO UPDATE SET
    recovery_phase = EXCLUDED.recovery_phase,
    vendor_delete_status = COALESCE(
      EXCLUDED.vendor_delete_status,
      app.graph_cleanup_tombstones.vendor_delete_status
    ),
    status = EXCLUDED.status,
    payload = COALESCE(app.graph_cleanup_tombstones.payload, '{}'::jsonb)
      || COALESCE(EXCLUDED.payload, '{}'::jsonb),
    updated_at = timezone('utc', now())
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$fn$;

COMMENT ON FUNCTION app.upsert_graph_cleanup_tombstone(uuid, uuid, text, text, text, text, text, jsonb) IS
  'Create or continue a 24h/7-day graph cleanup tombstone. Idempotent for open rows.';

CREATE OR REPLACE FUNCTION app.switch_graph_document_version(
  p_document_id uuid,
  p_new_version_id uuid,
  p_old_version_id uuid,
  p_expected_generation bigint,
  p_expected_workspace_key text
)
RETURNS TABLE (
  new_generation bigint,
  workspace_id uuid,
  switched boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_pointer app.graph_active_workspace_pointer%ROWTYPE;
  v_doc app.documents%ROWTYPE;
  v_new app.document_versions%ROWTYPE;
  v_old app.document_versions%ROWTYPE;
  v_ws app.graph_workspaces%ROWTYPE;
  v_auth bigint;
BEGIN
  PERFORM pg_advisory_xact_lock(
    hashtext('smart-rag-graph-pointer-v1'),
    hashtext(COALESCE(p_expected_workspace_key, 'company_default'))
  );

  SELECT * INTO v_pointer
  FROM app.graph_active_workspace_pointer
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'pointer_missing';
  END IF;

  IF v_pointer.generation IS DISTINCT FROM p_expected_generation THEN
    RAISE EXCEPTION 'stale_generation';
  END IF;

  SELECT * INTO v_ws
  FROM app.graph_workspaces
  WHERE id = v_pointer.workspace_id
  FOR UPDATE;

  IF v_pointer.workspace_id IS NOT NULL THEN
    IF NOT FOUND OR v_ws.workspace_key IS DISTINCT FROM p_expected_workspace_key THEN
      RAISE EXCEPTION 'workspace_mismatch';
    END IF;
    IF v_ws.state IN (
      'quarantined'::app.graph_workspace_state,
      'disabled'::app.graph_workspace_state,
      'retired'::app.graph_workspace_state
    ) THEN
      RAISE EXCEPTION 'workspace_not_switchable';
    END IF;
  END IF;

  SELECT * INTO v_doc
  FROM app.documents
  WHERE id = p_document_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'document_missing';
  END IF;

  IF v_doc.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'document_deleted';
  END IF;

  IF v_doc.visibility = 'restricted'::app.document_visibility THEN
    RAISE EXCEPTION 'document_restricted';
  END IF;

  IF v_doc.current_version_id IS DISTINCT FROM p_old_version_id THEN
    RAISE EXCEPTION 'current_version_mismatch';
  END IF;

  IF p_old_version_id IS NOT DISTINCT FROM p_new_version_id THEN
    RAISE EXCEPTION 'versions_not_distinct';
  END IF;

  SELECT * INTO v_old
  FROM app.document_versions
  WHERE id = p_old_version_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'old_version_missing';
  END IF;

  SELECT * INTO v_new
  FROM app.document_versions
  WHERE id = p_new_version_id
  FOR UPDATE;

  IF NOT FOUND OR v_new.document_id IS DISTINCT FROM p_document_id THEN
    RAISE EXCEPTION 'new_version_missing';
  END IF;

  IF v_new.deleted_at IS NOT NULL OR v_new.graph_eligible IS NOT TRUE THEN
    RAISE EXCEPTION 'new_version_ineligible';
  END IF;

  IF v_new.status NOT IN (
    'graph_pending'::app.document_status,
    'graph_ready'::app.document_status
  ) THEN
    RAISE EXCEPTION 'new_version_not_mapped';
  END IF;

  UPDATE app.document_versions
  SET
    is_current = false,
    updated_at = v_now
  WHERE document_id = p_document_id
    AND is_current = true
    AND id IS DISTINCT FROM p_new_version_id;

  UPDATE app.document_versions
  SET
    is_current = true,
    retrieval_eligible = true,
    status = 'graph_ready'::app.document_status,
    updated_at = v_now
  WHERE id = p_new_version_id;

  UPDATE app.documents
  SET
    current_version_id = p_new_version_id,
    visibility_generation = visibility_generation + 1,
    updated_at = v_now
  WHERE id = p_document_id;

  UPDATE app.company_settings
  SET
    authorization_version = authorization_version + 1,
    visibility_generation = visibility_generation + 1,
    updated_at = v_now
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
  RETURNING authorization_version INTO v_auth;

  UPDATE app.lightrag_source_map
  SET
    version_id = p_new_version_id,
    lightrag_doc_id = p_new_version_id::text,
    retrieval_eligible = true,
    mapped_at = v_now
  WHERE document_id = p_document_id;

  UPDATE app.lightrag_chunk_map
  SET retrieval_eligible = false
  WHERE version_id = p_old_version_id
    AND retrieval_eligible IS TRUE;

  UPDATE app.graph_evidence_map
  SET retrieval_eligible = false
  WHERE version_id = p_old_version_id
    AND retrieval_eligible IS TRUE;

  UPDATE app.lightrag_chunk_map
  SET retrieval_eligible = true
  WHERE version_id = p_new_version_id;

  UPDATE app.graph_evidence_map
  SET retrieval_eligible = true
  WHERE version_id = p_new_version_id;

  INSERT INTO app.bm25_index_jobs (
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    p_new_version_id,
    'upsert'::app.bm25_job_operation,
    'high'::app.job_priority,
    format('switch-upsert:%s:%s', p_new_version_id, v_doc.visibility_generation + 1),
    jsonb_build_object('reason', 'graph_version_switch', 'document_id', p_document_id)
  )
  ON CONFLICT (idempotency_key) DO NOTHING;

  INSERT INTO app.bm25_index_jobs (
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    p_old_version_id,
    'delete'::app.bm25_job_operation,
    'high'::app.job_priority,
    format('switch-delete:%s:%s', p_old_version_id, v_doc.visibility_generation + 1),
    jsonb_build_object('reason', 'graph_version_switch', 'document_id', p_document_id)
  )
  ON CONFLICT (idempotency_key) DO NOTHING;

  INSERT INTO app.lightrag_index_jobs (
    document_id,
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    p_document_id,
    p_old_version_id,
    'remove'::app.lightrag_job_operation,
    'high'::app.job_priority,
    format('graph_remove_after_switch:%s:%s', p_old_version_id, p_expected_generation),
    jsonb_build_object(
      'reason', 'version_supersede',
      'document_id', p_document_id,
      'version_id', p_old_version_id,
      'expected_generation', p_expected_generation,
      'post_flip_cleanup', true
    )
  )
  ON CONFLICT (idempotency_key) DO NOTHING;

  PERFORM app.upsert_graph_cleanup_tombstone(
    p_document_id,
    p_old_version_id,
    COALESCE(p_expected_workspace_key, 'company_default'),
    'version_supersede',
    'tombstone',
    NULL,
    'pending',
    jsonb_build_object('new_version_id', p_new_version_id)
  );

  PERFORM app.append_audit_event(
    'graph.pointer.version_switched',
    NULL,
    NULL,
    'document',
    p_document_id,
    v_auth,
    jsonb_build_object(
      'old_version_id', p_old_version_id,
      'new_version_id', p_new_version_id,
      'generation', v_pointer.generation,
      'workspace_key', p_expected_workspace_key
    )
  );

  new_generation := v_pointer.generation;
  workspace_id := v_pointer.workspace_id;
  switched := true;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.switch_graph_document_version(uuid, uuid, uuid, bigint, text) IS
  'Short pointer txn: lock FOR UPDATE, CAS generation, flip exactly one current version. Does not bump generation. Vendor delete runs after commit.';

CREATE OR REPLACE FUNCTION app.switch_graph_active_workspace(
  p_expected_generation bigint,
  p_expected_workspace_key text,
  p_target_workspace_key text
)
RETURNS TABLE (
  new_generation bigint,
  old_workspace_id uuid,
  new_workspace_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_pointer app.graph_active_workspace_pointer%ROWTYPE;
  v_old app.graph_workspaces%ROWTYPE;
  v_new app.graph_workspaces%ROWTYPE;
  v_auth bigint;
BEGIN
  PERFORM pg_advisory_xact_lock(
    hashtext('smart-rag-graph-pointer-v1'),
    hashtext(COALESCE(p_expected_workspace_key, 'company_default'))
  );

  SELECT * INTO v_pointer
  FROM app.graph_active_workspace_pointer
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'pointer_missing';
  END IF;

  IF v_pointer.generation IS DISTINCT FROM p_expected_generation THEN
    RAISE EXCEPTION 'stale_generation';
  END IF;

  IF p_target_workspace_key IS NULL OR btrim(p_target_workspace_key) = '' THEN
    RAISE EXCEPTION 'target_workspace_missing';
  END IF;

  IF p_target_workspace_key = p_expected_workspace_key THEN
    RAISE EXCEPTION 'target_workspace_unchanged';
  END IF;

  IF v_pointer.workspace_id IS NOT NULL THEN
    SELECT * INTO v_old
    FROM app.graph_workspaces
    WHERE id = v_pointer.workspace_id
    FOR UPDATE;
    IF NOT FOUND OR v_old.workspace_key IS DISTINCT FROM p_expected_workspace_key THEN
      RAISE EXCEPTION 'workspace_mismatch';
    END IF;
  END IF;

  SELECT * INTO v_new
  FROM app.graph_workspaces
  WHERE workspace_key = p_target_workspace_key
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'target_workspace_missing';
  END IF;

  IF v_new.state IN (
    'quarantined'::app.graph_workspace_state,
    'disabled'::app.graph_workspace_state,
    'retired'::app.graph_workspace_state
  ) THEN
    RAISE EXCEPTION 'target_workspace_not_switchable';
  END IF;

  IF v_new.embedding_model IS DISTINCT FROM 'text-embedding-3-large'
    OR v_new.embedding_dimensions IS DISTINCT FROM 1024
  THEN
    RAISE EXCEPTION 'embedding_config_mismatch';
  END IF;

  IF v_old.id IS NOT NULL
    AND (
      v_old.embedding_model IS DISTINCT FROM v_new.embedding_model
      OR v_old.embedding_dimensions IS DISTINCT FROM v_new.embedding_dimensions
    )
  THEN
    RAISE EXCEPTION 'in_place_mixed_embeddings_forbidden';
  END IF;

  UPDATE app.graph_active_workspace_pointer
  SET
    workspace_id = v_new.id,
    generation = generation + 1,
    updated_at = v_now
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid
    AND generation = p_expected_generation
  RETURNING * INTO v_pointer;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'stale_generation';
  END IF;

  UPDATE app.graph_workspaces
  SET
    state = 'active'::app.graph_workspace_state,
    updated_at = v_now
  WHERE id = v_new.id;

  IF v_old.id IS NOT NULL THEN
    UPDATE app.graph_workspaces
    SET
      state = 'retired'::app.graph_workspace_state,
      updated_at = v_now
    WHERE id = v_old.id
      AND state IS DISTINCT FROM 'retired'::app.graph_workspace_state;
  END IF;

  SELECT authorization_version
  INTO v_auth
  FROM app.company_settings
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;

  PERFORM app.append_audit_event(
    'graph.pointer.workspace_switched',
    NULL,
    NULL,
    'graph_workspace',
    v_new.id,
    v_auth,
    jsonb_build_object(
      'old_workspace_key', p_expected_workspace_key,
      'new_workspace_key', p_target_workspace_key,
      'old_generation', p_expected_generation,
      'new_generation', v_pointer.generation
    )
  );

  new_generation := v_pointer.generation;
  old_workspace_id := v_old.id;
  new_workspace_id := v_new.id;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.switch_graph_active_workspace(bigint, text, text) IS
  'Short pointer txn: CAS generation, attach exactly one workspace, retire the previous. Homogeneous embedding pin required.';

CREATE OR REPLACE FUNCTION app.disable_graph_workspace(
  p_workspace_key text,
  p_reason text
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_id uuid;
  v_auth bigint;
BEGIN
  UPDATE app.graph_workspaces AS ws
  SET
    state = 'disabled'::app.graph_workspace_state,
    config_snapshot = COALESCE(ws.config_snapshot, '{}'::jsonb) || jsonb_build_object(
      'disabled_reason', left(COALESCE(p_reason, 'unspecified'), 512),
      'disabled_at', timezone('utc', now())
    ),
    updated_at = timezone('utc', now())
  WHERE ws.workspace_key = p_workspace_key
    AND ws.state IS DISTINCT FROM 'retired'::app.graph_workspace_state
  RETURNING ws.id INTO v_id;

  SELECT authorization_version
  INTO v_auth
  FROM app.company_settings
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;

  IF v_id IS NOT NULL THEN
    PERFORM app.append_audit_event(
      'graph.workspace.disabled',
      NULL,
      NULL,
      'graph_workspace',
      v_id,
      v_auth,
      jsonb_build_object(
        'workspace_key', p_workspace_key,
        'reason', left(COALESCE(p_reason, ''), 512)
      )
    );
  END IF;

  RETURN v_id;
END;
$fn$;

COMMENT ON FUNCTION app.disable_graph_workspace(text, text) IS
  'Disable a workspace. Query/inspection emit graph_outage. Repair/admin rows remain.';

CREATE OR REPLACE FUNCTION app.record_graph_upgrade_qualification(
  p_candidate_database text,
  p_candidate_schema text,
  p_runtime_database text,
  p_runtime_schema text,
  p_status text DEFAULT 'recorded',
  p_notes text DEFAULT ''
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_id uuid;
  v_status text := COALESCE(p_status, 'recorded');
  v_failures integer := 0;
BEGIN
  IF btrim(p_candidate_database) = btrim(p_runtime_database)
    AND btrim(p_candidate_schema) = btrim(p_runtime_schema)
  THEN
    v_status := 'refused_same_schema';
    INSERT INTO app.graph_upgrade_qualifications (
      candidate_database,
      candidate_schema,
      runtime_database,
      runtime_schema,
      status,
      notes
    )
    VALUES (
      p_candidate_database,
      p_candidate_schema,
      p_runtime_database,
      p_runtime_schema,
      v_status,
      'second workspace in the same schema is not upgrade proof'
    )
    RETURNING id INTO v_id;
    RETURN v_id;
  END IF;

  SELECT q.consecutive_failures
  INTO v_failures
  FROM app.graph_upgrade_qualifications AS q
  WHERE q.runtime_database = p_runtime_database
    AND q.runtime_schema = p_runtime_schema
  ORDER BY q.created_at DESC
  LIMIT 1;

  v_failures := COALESCE(v_failures, 0);
  IF v_status = 'failed' THEN
    v_failures := v_failures + 1;
  ELSIF v_status = 'passed' THEN
    v_failures := 0;
  END IF;

  IF v_failures >= 2 THEN
    v_status := 'disable_review';
  END IF;

  INSERT INTO app.graph_upgrade_qualifications (
    candidate_database,
    candidate_schema,
    runtime_database,
    runtime_schema,
    status,
    consecutive_failures,
    notes
  )
  VALUES (
    p_candidate_database,
    p_candidate_schema,
    p_runtime_database,
    p_runtime_schema,
    v_status,
    v_failures,
    left(COALESCE(p_notes, ''), 512)
  )
  RETURNING id INTO v_id;

  RETURN v_id;
END;
$fn$;

COMMENT ON FUNCTION app.record_graph_upgrade_qualification(text, text, text, text, text, text) IS
  'Record isolated upgrade proof. Same-database same-schema (runtime lightrag) is recorded as refused_same_schema. Two consecutive failures open disable review.';

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
      AND COALESCE(gem.retrieval_eligible, true) IS TRUE
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

REVOKE ALL ON FUNCTION app.assert_graph_build_index_allowed(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.mark_graph_maps_ineligible_for_version(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.upsert_graph_cleanup_tombstone(uuid, uuid, text, text, text, text, text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.switch_graph_document_version(uuid, uuid, uuid, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.switch_graph_active_workspace(bigint, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.disable_graph_workspace(text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.record_graph_upgrade_qualification(text, text, text, text, text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.assert_graph_build_index_allowed(uuid, uuid) TO app_worker;
GRANT EXECUTE ON FUNCTION app.mark_graph_maps_ineligible_for_version(uuid) TO app_worker;
GRANT EXECUTE ON FUNCTION app.upsert_graph_cleanup_tombstone(uuid, uuid, text, text, text, text, text, jsonb) TO app_worker;
GRANT EXECUTE ON FUNCTION app.switch_graph_document_version(uuid, uuid, uuid, bigint, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.switch_graph_active_workspace(bigint, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.disable_graph_workspace(text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.record_graph_upgrade_qualification(text, text, text, text, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.assert_graph_build_index_allowed(uuid, uuid) TO app_api;

COMMENT ON FUNCTION app.inspect_graph_neighborhood(
  uuid, text, bigint, text, text, text[], uuid, integer, integer
) IS
  'SQL-level graph inspection: depth 3, 200 rows, 3s statement_timeout. Drops ineligible maps. No vendor prose.';

GRANT EXECUTE ON FUNCTION app.inspect_graph_neighborhood(
  uuid, text, bigint, text, text, text[], uuid, integer, integer
) TO app_api;
