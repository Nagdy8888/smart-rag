-- Phase 3 Packet 3: scan evidence columns, promotion saga ledger, upload finalize RPCs.

ALTER TYPE app.scan_result ADD VALUE IF NOT EXISTS 'hash_mismatch';

ALTER TABLE app.document_scan_events
  ADD COLUMN IF NOT EXISTS bytes_examined bigint,
  ADD COLUMN IF NOT EXISTS config_version text,
  ADD COLUMN IF NOT EXISTS signature_db_ids jsonb NOT NULL DEFAULT '{}'::jsonb;

DO $scan_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'document_scan_events_bytes_examined_nonneg'
  ) THEN
    ALTER TABLE app.document_scan_events
      ADD CONSTRAINT document_scan_events_bytes_examined_nonneg
      CHECK (bytes_examined IS NULL OR bytes_examined >= 0);
  END IF;
END;
$scan_constraints$;

COMMENT ON COLUMN app.document_scan_events.bytes_examined IS
  'Bytes examined by the scanner for this event.';
COMMENT ON COLUMN app.document_scan_events.config_version IS
  'Pinned scan limit/config version identifier from INGESTION_LIMITS.';
COMMENT ON COLUMN app.document_scan_events.signature_db_ids IS
  'Signature database ids/versions/timestamps at scan time.';

CREATE TABLE IF NOT EXISTS app.storage_promotion_sagas (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  idempotency_key text NOT NULL,
  quarantine_bucket text NOT NULL,
  quarantine_path text NOT NULL,
  destination_bucket text NOT NULL,
  destination_path text NOT NULL,
  expected_hash text NOT NULL,
  expected_bytes bigint NOT NULL,
  current_step text NOT NULL DEFAULT 'intent',
  reservation_id uuid REFERENCES app.upload_quota_reservations (id) ON DELETE SET NULL,
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT storage_promotion_sagas_idempotency_uq UNIQUE (idempotency_key),
  CONSTRAINT storage_promotion_sagas_expected_bytes_positive CHECK (expected_bytes > 0),
  CONSTRAINT storage_promotion_sagas_step_check CHECK (
    current_step IN (
      'intent',
      'copy_done',
      'verify_done',
      'db_switched',
      'source_deleted',
      'completed'
    )
  )
);

COMMENT ON TABLE app.storage_promotion_sagas IS
  'Resumable Storage promotion saga ledger; one authoritative destination per version.';

CREATE INDEX IF NOT EXISTS storage_promotion_sagas_version_idx
  ON app.storage_promotion_sagas (version_id);

CREATE TRIGGER storage_promotion_sagas_touch_updated_at
  BEFORE UPDATE ON app.storage_promotion_sagas
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

ALTER TABLE app.storage_promotion_sagas ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.storage_promotion_sagas FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS storage_promotion_sagas_worker_all ON app.storage_promotion_sagas;
CREATE POLICY storage_promotion_sagas_worker_all
  ON app.storage_promotion_sagas
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS storage_promotion_sagas_api_select ON app.storage_promotion_sagas;
CREATE POLICY storage_promotion_sagas_api_select
  ON app.storage_promotion_sagas
  FOR SELECT
  TO app_api
  USING (true);

CREATE OR REPLACE FUNCTION app.transition_document_version_status(
  p_version_id uuid,
  p_expected_status app.document_status,
  p_new_status app.document_status
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  updated_count integer;
BEGIN
  UPDATE app.document_versions AS dv
  SET status = p_new_status,
      updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id
    AND dv.status = p_expected_status;

  GET DIAGNOSTICS updated_count = ROW_COUNT;
  RETURN updated_count = 1;
END;
$fn$;

COMMENT ON FUNCTION app.transition_document_version_status(uuid, app.document_status, app.document_status) IS
  'Atomic compare-and-set for ingestion lifecycle transitions.';

CREATE OR REPLACE FUNCTION app.upsert_promotion_saga_intent(
  p_version_id uuid,
  p_idempotency_key text,
  p_quarantine_bucket text,
  p_quarantine_path text,
  p_destination_bucket text,
  p_destination_path text,
  p_expected_hash text,
  p_expected_bytes bigint,
  p_reservation_id uuid DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  saga_id uuid;
BEGIN
  IF p_idempotency_key IS NULL OR btrim(p_idempotency_key) = '' THEN
    RAISE EXCEPTION 'promotion idempotency_key required';
  END IF;

  INSERT INTO app.storage_promotion_sagas (
    version_id,
    idempotency_key,
    quarantine_bucket,
    quarantine_path,
    destination_bucket,
    destination_path,
    expected_hash,
    expected_bytes,
    reservation_id,
    current_step
  )
  VALUES (
    p_version_id,
    p_idempotency_key,
    p_quarantine_bucket,
    p_quarantine_path,
    p_destination_bucket,
    p_destination_path,
    p_expected_hash,
    p_expected_bytes,
    p_reservation_id,
    'intent'
  )
  ON CONFLICT (idempotency_key) DO UPDATE
  SET updated_at = timezone('utc', now())
  RETURNING id INTO saga_id;

  RETURN saga_id;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.advance_promotion_saga_step(
  p_saga_id uuid,
  p_expected_step text,
  p_new_step text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  updated_count integer;
BEGIN
  UPDATE app.storage_promotion_sagas AS s
  SET current_step = p_new_step,
      completed_at = CASE
        WHEN p_new_step = 'completed' THEN timezone('utc', now())
        ELSE s.completed_at
      END,
      updated_at = timezone('utc', now())
  WHERE s.id = p_saga_id
    AND s.current_step = p_expected_step;

  GET DIAGNOSTICS updated_count = ROW_COUNT;
  RETURN updated_count = 1;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.complete_promotion_db_switch(
  p_saga_id uuid,
  p_version_id uuid,
  p_destination_bucket text,
  p_destination_path text,
  p_content_hash text,
  p_byte_size bigint,
  p_media_type text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  switched boolean;
BEGIN
  switched := app.advance_promotion_saga_step(p_saga_id, 'verify_done', 'db_switched');
  IF NOT switched THEN
    IF EXISTS (
      SELECT 1
      FROM app.storage_promotion_sagas AS s
      WHERE s.id = p_saga_id
        AND s.current_step IN ('db_switched', 'source_deleted', 'completed')
    ) THEN
      RETURN true;
    END IF;
    RETURN false;
  END IF;

  UPDATE app.document_versions AS dv
  SET
    storage_bucket = p_destination_bucket,
    storage_path = p_destination_path,
    content_hash = p_content_hash,
    byte_size = p_byte_size,
    media_type = coalesce(p_media_type, dv.media_type),
    status = 'parsing'::app.document_status,
    updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id;

  RETURN true;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.finalize_quarantine_upload(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  reservation_id uuid,
  object_name text,
  content_hash text,
  actual_bytes bigint,
  media_type text,
  declared_category text,
  attestation_policy_version text,
  idempotency_key text,
  document_title text DEFAULT NULL
)
RETURNS TABLE (
  document_id uuid,
  version_id uuid,
  job_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  reservation app.upload_quota_reservations%ROWTYPE;
  expected_prefix text;
  new_document_id uuid;
  new_version_id uuid;
  new_job_id uuid;
  safe_title text;
  safe_filename text;
  destination_path text;
  job_key text;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  IF content_hash IS NULL OR length(btrim(content_hash)) <> 64 THEN
    RAISE EXCEPTION 'content_hash must be 64-char sha256 hex';
  END IF;

  IF actual_bytes IS NULL OR actual_bytes <= 0 THEN
    RAISE EXCEPTION 'actual_bytes must be positive';
  END IF;

  IF idempotency_key IS NULL OR btrim(idempotency_key) = '' THEN
    RAISE EXCEPTION 'idempotency_key required';
  END IF;

  SELECT * INTO reservation
  FROM app.upload_quota_reservations AS r
  WHERE r.id = finalize_quarantine_upload.reservation_id
    AND r.user_id = caller_user_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'reservation not found for caller';
  END IF;

  IF reservation.status <> 'committed'::app.budget_reservation_status THEN
    RAISE EXCEPTION 'reservation must be committed before finalize';
  END IF;

  IF reservation.cleanup_status = 'pending' THEN
    RAISE EXCEPTION 'over-limit reservation cannot finalize ingestion';
  END IF;

  expected_prefix := caller_user_id::text || '/' || reservation.id::text || '/';
  IF object_name IS NULL
    OR NOT object_name LIKE expected_prefix || '%' THEN
    RAISE EXCEPTION 'object_name must be under reservation prefix';
  END IF;

  safe_filename := regexp_replace(
    split_part(object_name, '/', array_length(string_to_array(object_name, '/'), 1)),
    '[^A-Za-z0-9._-]',
    '_',
    'g'
  );
  IF safe_filename = '' THEN
    safe_filename := 'upload.bin';
  END IF;

  safe_title := coalesce(
    nullif(btrim(document_title), ''),
    safe_filename
  );

  SELECT j.id
  INTO new_job_id
  FROM app.ingestion_jobs AS j
  WHERE j.idempotency_key = finalize_quarantine_upload.idempotency_key;

  IF FOUND THEN
    SELECT j.document_id, j.version_id
    INTO new_document_id, new_version_id
    FROM app.ingestion_jobs AS j
    WHERE j.id = new_job_id;
    document_id := new_document_id;
    version_id := new_version_id;
    job_id := new_job_id;
    RETURN NEXT;
    RETURN;
  END IF;

  new_document_id := gen_random_uuid();
  new_version_id := gen_random_uuid();
  destination_path := format(
    'documents/%s/versions/%s/%s',
    new_document_id,
    new_version_id,
    safe_filename
  );
  job_key := finalize_quarantine_upload.idempotency_key;

  INSERT INTO app.documents (
    id,
    title,
    created_by
  )
  VALUES (
    new_document_id,
    safe_title,
    caller_user_id
  );

  INSERT INTO app.document_versions (
    id,
    document_id,
    version_number,
    status,
    storage_bucket,
    storage_path,
    content_hash,
    media_type,
    byte_size,
    created_by
  )
  VALUES (
    new_version_id,
    new_document_id,
    1,
    'uploaded'::app.document_status,
    coalesce(reservation.storage_bucket, 'documents-quarantine'),
    object_name,
    lower(content_hash),
    media_type,
    actual_bytes,
    caller_user_id
  );

  INSERT INTO app.document_sources (
    document_id,
    version_id,
    source_type,
    declared_category
  )
  VALUES (
    new_document_id,
    new_version_id,
    'file_upload'::app.source_type,
    declared_category
  );

  INSERT INTO app.audit_events (
    event_type,
    actor_user_id,
    actor_role,
    target_type,
    target_id,
    authorization_version,
    payload
  )
  VALUES (
    'quarantine_upload_finalized',
    caller_user_id,
    caller_role::app.user_role,
    'document_version',
    new_version_id,
    caller_authorization_version,
    jsonb_build_object(
      'reservation_id', reservation.id,
      'object_name', object_name,
      'content_hash', lower(content_hash),
      'actual_bytes', actual_bytes,
      'declared_category', declared_category,
      'attestation_policy_version', attestation_policy_version,
      'destination_path', destination_path
    )
  );

  INSERT INTO app.ingestion_jobs (
    document_id,
    version_id,
    job_kind,
    idempotency_key,
    payload_ref
  )
  VALUES (
    new_document_id,
    new_version_id,
    'scan_promote',
    job_key,
    jsonb_build_object(
      'operation_key', job_key,
      'storage_bucket', coalesce(reservation.storage_bucket, 'documents-quarantine'),
      'storage_path', object_name,
      'content_hash', lower(content_hash),
      'byte_size', actual_bytes,
      'media_type', media_type,
      'reservation_id', reservation.id,
      'destination_bucket', 'documents-originals',
      'destination_path', destination_path,
      'declared_category', declared_category,
      'attestation_policy_version', attestation_policy_version,
      'uploader_user_id', caller_user_id
    )
  )
  RETURNING id INTO new_job_id;

  document_id := new_document_id;
  version_id := new_version_id;
  job_id := new_job_id;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.finalize_quarantine_upload IS
  'Phase 3 upload finalization: verify reservation/path, create version/job, audit.';

REVOKE ALL ON FUNCTION app.transition_document_version_status(uuid, app.document_status, app.document_status) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.upsert_promotion_saga_intent(uuid, text, text, text, text, text, text, bigint, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.advance_promotion_saga_step(uuid, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.complete_promotion_db_switch(uuid, uuid, text, text, text, bigint, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.finalize_quarantine_upload(uuid, text, bigint, uuid, text, text, bigint, text, text, text, text, text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.transition_document_version_status(uuid, app.document_status, app.document_status) TO app_worker;
GRANT EXECUTE ON FUNCTION app.upsert_promotion_saga_intent(uuid, text, text, text, text, text, text, bigint, uuid) TO app_worker;
GRANT EXECUTE ON FUNCTION app.advance_promotion_saga_step(uuid, text, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.complete_promotion_db_switch(uuid, uuid, text, text, text, bigint, text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.finalize_quarantine_upload(uuid, text, bigint, uuid, text, text, bigint, text, text, text, text, text) TO app_api;

GRANT SELECT, INSERT, UPDATE ON app.storage_promotion_sagas TO app_worker;
GRANT SELECT ON app.storage_promotion_sagas TO app_api;
