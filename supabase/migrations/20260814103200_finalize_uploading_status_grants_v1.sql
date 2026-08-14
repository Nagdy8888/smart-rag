-- Phase 3 gap close-out Run 3: finalize uploading→uploaded; cleanup uploading
-- versions with expired quota; app_api status-read grants.

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
  switched boolean;
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

  IF reservation.version_id IS NOT NULL AND reservation.document_id IS NOT NULL THEN
    new_document_id := reservation.document_id;
    new_version_id := reservation.version_id;
    UPDATE app.documents
    SET title = safe_title, updated_at = timezone('utc', now())
    WHERE id = new_document_id;
    switched := app.transition_document_version_status(
      new_version_id,
      'uploading'::app.document_status,
      'uploaded'::app.document_status
    );
    IF NOT switched THEN
      IF NOT EXISTS (
        SELECT 1
        FROM app.document_versions AS dv
        WHERE dv.id = new_version_id
          AND dv.status = 'uploaded'::app.document_status
      ) THEN
        RAISE EXCEPTION 'uploading version missing or already advanced';
      END IF;
    END IF;
    UPDATE app.document_versions AS dv
    SET
      storage_bucket = coalesce(reservation.storage_bucket, 'documents-quarantine'),
      storage_path = object_name,
      content_hash = lower(finalize_quarantine_upload.content_hash),
      media_type = finalize_quarantine_upload.media_type,
      byte_size = actual_bytes,
      updated_at = timezone('utc', now())
    WHERE dv.id = new_version_id;
  ELSE
    new_document_id := gen_random_uuid();
    new_version_id := gen_random_uuid();
    INSERT INTO app.documents (id, title, created_by)
    VALUES (new_document_id, safe_title, caller_user_id);
    INSERT INTO app.document_versions (
      id, document_id, version_number, status, storage_bucket, storage_path,
      content_hash, media_type, byte_size, created_by
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
  END IF;

  destination_path := format(
    'documents/%s/versions/%s/%s',
    new_document_id,
    new_version_id,
    safe_filename
  );
  job_key := finalize_quarantine_upload.idempotency_key;

  INSERT INTO app.document_sources (
    document_id, version_id, source_type, declared_category
  )
  SELECT
    new_document_id,
    new_version_id,
    'file_upload'::app.source_type,
    declared_category
  WHERE NOT EXISTS (
    SELECT 1
    FROM app.document_sources AS ds
    WHERE ds.version_id = new_version_id
      AND ds.source_type = 'file_upload'::app.source_type
  );

  INSERT INTO app.audit_events (
    event_type, actor_user_id, actor_role, target_type, target_id,
    authorization_version, payload
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
    document_id, version_id, job_kind, idempotency_key, payload_ref
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

CREATE OR REPLACE FUNCTION app.release_expired_upload_reservations(
  as_of timestamptz DEFAULT timezone('utc', now())
)
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  released_count integer;
BEGIN
  UPDATE app.upload_quota_reservations AS r
  SET
    status = 'expired'::app.budget_reservation_status,
    released_at = coalesce(r.released_at, as_of),
    cleanup_status = CASE
      WHEN r.cleanup_status IS NULL THEN 'pending'
      ELSE r.cleanup_status
    END,
    updated_at = timezone('utc', now())
  WHERE r.status = 'reserved'::app.budget_reservation_status
    AND r.expires_at <= as_of;

  GET DIAGNOSTICS released_count = ROW_COUNT;

  UPDATE app.documents AS d
  SET current_version_id = NULL, updated_at = timezone('utc', now())
  WHERE d.current_version_id IN (
    SELECT r.version_id
    FROM app.upload_quota_reservations AS r
    WHERE r.status = 'expired'::app.budget_reservation_status
      AND r.version_id IS NOT NULL
  );

  DELETE FROM app.document_versions AS dv
  WHERE dv.status = 'uploading'::app.document_status
    AND dv.id IN (
      SELECT r.version_id
      FROM app.upload_quota_reservations AS r
      WHERE r.status = 'expired'::app.budget_reservation_status
        AND r.version_id IS NOT NULL
    );

  DELETE FROM app.documents AS d
  WHERE d.current_version_id IS NULL
    AND NOT EXISTS (
      SELECT 1
      FROM app.document_versions AS remain
      WHERE remain.document_id = d.id
    )
    AND EXISTS (
      SELECT 1
      FROM app.upload_quota_reservations AS r
      WHERE r.document_id = d.id
        AND r.status = 'expired'::app.budget_reservation_status
    );

  RETURN coalesce(released_count, 0);
END;
$fn$;

GRANT SELECT ON app.document_versions TO app_api;
GRANT SELECT ON app.document_chunks TO app_api;
GRANT SELECT ON app.document_tables TO app_api;
GRANT SELECT ON app.document_sources TO app_api;
GRANT SELECT ON app.document_scan_events TO app_api;
GRANT SELECT ON app.ingestion_jobs TO app_api;
GRANT SELECT ON app.embedding_operation_ledger TO app_api;
GRANT SELECT ON app.bm25_index_jobs TO app_api;
GRANT SELECT ON app.bm25_index_versions TO app_api;
GRANT SELECT ON app.lightrag_index_jobs TO app_api;
GRANT SELECT ON app.source_approval_requests TO app_api;

DROP POLICY IF EXISTS document_versions_api_status_read ON app.document_versions;
CREATE POLICY document_versions_api_status_read
  ON app.document_versions
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_chunks_api_status_read ON app.document_chunks;
CREATE POLICY document_chunks_api_status_read
  ON app.document_chunks
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_tables_api_status_read ON app.document_tables;
CREATE POLICY document_tables_api_status_read
  ON app.document_tables
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_sources_api_status_read ON app.document_sources;
CREATE POLICY document_sources_api_status_read
  ON app.document_sources
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_scan_events_api_status_read ON app.document_scan_events;
CREATE POLICY document_scan_events_api_status_read
  ON app.document_scan_events
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS ingestion_jobs_api_status_read ON app.ingestion_jobs;
CREATE POLICY ingestion_jobs_api_status_read
  ON app.ingestion_jobs
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS embedding_ledger_api_status_read ON app.embedding_operation_ledger;
CREATE POLICY embedding_ledger_api_status_read
  ON app.embedding_operation_ledger
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS bm25_jobs_api_status_read ON app.bm25_index_jobs;
CREATE POLICY bm25_jobs_api_status_read
  ON app.bm25_index_jobs
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS bm25_versions_api_status_read ON app.bm25_index_versions;
CREATE POLICY bm25_versions_api_status_read
  ON app.bm25_index_versions
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS lightrag_jobs_api_status_read ON app.lightrag_index_jobs;
CREATE POLICY lightrag_jobs_api_status_read
  ON app.lightrag_index_jobs
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS source_approvals_api_status_read ON app.source_approval_requests;
CREATE POLICY source_approvals_api_status_read
  ON app.source_approval_requests
  FOR SELECT
  TO app_api
  USING (true);
