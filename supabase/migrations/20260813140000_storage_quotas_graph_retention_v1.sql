-- Phase 2 Packet 5: private Storage buckets, upload quotas, scan foundations,
-- graph eligibility RPCs, retention structures, admin notification helper.
--
-- Path contracts (all buckets public=false):
--   documents-quarantine: {auth.uid()}/{reservation_id}/{safe_filename}
--   documents-originals:  documents/{document_id}/versions/{version_id}/{safe_filename}
--   web-snapshots:        sources/{source_id}/crawls/{crawl_version}/{safe_filename}
--   table-artifacts:      documents/{document_id}/versions/{version_id}/tables/{sheet}/{safe_filename}
--   exports:              exports/{user_id}/{export_id}/{safe_filename}

-- ---------------------------------------------------------------------------
-- Private buckets (idempotent)
-- ---------------------------------------------------------------------------

INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES
  ('documents-quarantine', 'documents-quarantine', false, NULL, NULL),
  ('documents-originals', 'documents-originals', false, NULL, NULL),
  ('web-snapshots', 'web-snapshots', false, NULL, NULL),
  ('table-artifacts', 'table-artifacts', false, NULL, NULL),
  ('exports', 'exports', false, 104857600, NULL)
ON CONFLICT (id) DO UPDATE
SET
  public = EXCLUDED.public,
  name = EXCLUDED.name,
  file_size_limit = COALESCE(EXCLUDED.file_size_limit, storage.buckets.file_size_limit);

-- ---------------------------------------------------------------------------
-- Upload quota reservation expansion
-- ---------------------------------------------------------------------------

ALTER TABLE app.upload_quota_reservations
  ADD COLUMN IF NOT EXISTS idempotency_key text,
  ADD COLUMN IF NOT EXISTS session_id text,
  ADD COLUMN IF NOT EXISTS actual_bytes bigint,
  ADD COLUMN IF NOT EXISTS finalized_at timestamptz,
  ADD COLUMN IF NOT EXISTS cleanup_status text;

COMMENT ON COLUMN app.upload_quota_reservations.reserved_bytes IS
  'Declared byte size at admission (advisory until finalize compares actual_bytes).';
COMMENT ON COLUMN app.upload_quota_reservations.idempotency_key IS
  'Caller-supplied idempotency key; unique per user when present.';
COMMENT ON COLUMN app.upload_quota_reservations.cleanup_status IS
  'null | pending | in_progress | done | failed - Storage API cleanup lifecycle.';

CREATE UNIQUE INDEX IF NOT EXISTS upload_quota_reservations_user_idempotency_uq
  ON app.upload_quota_reservations (user_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

DO $constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'upload_quota_reservations_cleanup_status_check'
  ) THEN
    ALTER TABLE app.upload_quota_reservations
      ADD CONSTRAINT upload_quota_reservations_cleanup_status_check
      CHECK (
        cleanup_status IS NULL
        OR cleanup_status IN ('pending', 'in_progress', 'done', 'failed')
      );
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'upload_quota_reservations_actual_bytes_nonneg'
  ) THEN
    ALTER TABLE app.upload_quota_reservations
      ADD CONSTRAINT upload_quota_reservations_actual_bytes_nonneg
      CHECK (actual_bytes IS NULL OR actual_bytes >= 0);
  END IF;
END;
$constraints$;

-- ---------------------------------------------------------------------------
-- Company retention defaults (Phase 1 signed defaults)
-- ---------------------------------------------------------------------------

ALTER TABLE app.company_settings
  ADD COLUMN IF NOT EXISTS retention_days integer NOT NULL DEFAULT 365,
  ADD COLUMN IF NOT EXISTS quarantine_ttl_hours integer NOT NULL DEFAULT 24,
  ADD COLUMN IF NOT EXISTS legal_hold_enabled boolean NOT NULL DEFAULT false;

DO $company_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'company_settings_retention_days_positive'
  ) THEN
    ALTER TABLE app.company_settings
      ADD CONSTRAINT company_settings_retention_days_positive
      CHECK (retention_days > 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'company_settings_quarantine_ttl_hours_positive'
  ) THEN
    ALTER TABLE app.company_settings
      ADD CONSTRAINT company_settings_quarantine_ttl_hours_positive
      CHECK (quarantine_ttl_hours > 0);
  END IF;
END;
$company_constraints$;

COMMENT ON COLUMN app.company_settings.retention_days IS
  'Phase 1 default undeleted corpus retention window (365 days). Purge workflows are later phases.';
COMMENT ON COLUMN app.company_settings.quarantine_ttl_hours IS
  'Never-finalized quarantine object TTL (default 24h) before Storage API cleanup.';
COMMENT ON COLUMN app.company_settings.legal_hold_enabled IS
  'Company-wide legal hold flag; Phase 2 structure only.';

-- ---------------------------------------------------------------------------
-- Retention / offboarding structures (Phase 2 schema only)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS app.retention_holds (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  resource_type text NOT NULL,
  resource_id uuid NOT NULL,
  reason text NOT NULL,
  held_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  released_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT retention_holds_resource_type_nonempty CHECK (btrim(resource_type) <> ''),
  CONSTRAINT retention_holds_reason_nonempty CHECK (btrim(reason) <> '')
);

CREATE INDEX IF NOT EXISTS retention_holds_resource_idx
  ON app.retention_holds (resource_type, resource_id)
  WHERE released_at IS NULL;

COMMENT ON TABLE app.retention_holds IS
  'Legal/compliance holds. Phase 2 structure; purge enforcement is later.';

CREATE TABLE IF NOT EXISTS app.offboarding_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  requested_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'pending',
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT offboarding_requests_status_check
    CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled'))
);

COMMENT ON TABLE app.offboarding_requests IS
  'User offboarding workflow shell. Phase 2 structure only; execution later.';

ALTER TABLE app.retention_holds ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.offboarding_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.retention_holds FORCE ROW LEVEL SECURITY;
ALTER TABLE app.offboarding_requests FORCE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Scan event provenance columns + immutability / fake-clean blockers
-- ---------------------------------------------------------------------------

ALTER TABLE app.document_scan_events
  ADD COLUMN IF NOT EXISTS uploader_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS session_id text,
  ADD COLUMN IF NOT EXISTS declared_category text,
  ADD COLUMN IF NOT EXISTS functionality_level text,
  ADD COLUMN IF NOT EXISTS signature_db_timestamp timestamptz,
  ADD COLUMN IF NOT EXISTS network_provenance jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN app.document_scan_events.uploader_user_id IS
  'Uploader subject at scan time; no long-retention raw content.';
COMMENT ON COLUMN app.document_scan_events.network_provenance IS
  'Network/source approval provenance metadata without raw payloads.';

CREATE OR REPLACE FUNCTION app.block_document_scan_events_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RAISE EXCEPTION 'document_scan_events is append-only';
END;
$fn$;

DROP TRIGGER IF EXISTS document_scan_events_block_update ON app.document_scan_events;
CREATE TRIGGER document_scan_events_block_update
  BEFORE UPDATE ON app.document_scan_events
  FOR EACH ROW
  EXECUTE FUNCTION app.block_document_scan_events_mutation();

DROP TRIGGER IF EXISTS document_scan_events_block_delete ON app.document_scan_events;
CREATE TRIGGER document_scan_events_block_delete
  BEFORE DELETE ON app.document_scan_events
  FOR EACH ROW
  EXECUTE FUNCTION app.block_document_scan_events_mutation();

CREATE OR REPLACE FUNCTION app.block_fake_clean_scan_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  session_role text := current_setting('role', true);
BEGIN
  IF NEW.result = 'clean'::app.scan_result THEN
    -- Phase 3 worker is the only producer of genuine clean evidence.
    IF session_role IS DISTINCT FROM 'app_worker'
      AND session_role IS DISTINCT FROM 'postgres'
      AND session_role IS DISTINCT FROM 'supabase_admin' THEN
      RAISE EXCEPTION
        'document_scan_events.result=clean requires Phase 3 worker evidence (role %)',
        coalesce(session_role, 'unknown');
    END IF;
  END IF;
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS document_scan_events_block_fake_clean ON app.document_scan_events;
CREATE TRIGGER document_scan_events_block_fake_clean
  BEFORE INSERT ON app.document_scan_events
  FOR EACH ROW
  EXECUTE FUNCTION app.block_fake_clean_scan_insert();

COMMENT ON FUNCTION app.block_fake_clean_scan_insert() IS
  'Rejects result=clean inserts from authenticated/app_api; Phase 3 app_worker only.';

-- ---------------------------------------------------------------------------
-- Quarantine path helper for Storage RLS (SECURITY DEFINER)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.quarantine_upload_path_allowed(object_name text)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app, storage
AS $fn$
DECLARE
  folders text[];
  reservation_id uuid;
  caller uuid := auth.uid();
BEGIN
  IF caller IS NULL OR object_name IS NULL OR btrim(object_name) = '' THEN
    RETURN false;
  END IF;

  folders := storage.foldername(object_name);
  IF coalesce(array_length(folders, 1), 0) < 2 THEN
    RETURN false;
  END IF;

  IF folders[1] IS DISTINCT FROM caller::text THEN
    RETURN false;
  END IF;

  BEGIN
    reservation_id := folders[2]::uuid;
  EXCEPTION
    WHEN invalid_text_representation THEN
      RETURN false;
  END;

  RETURN EXISTS (
    SELECT 1
    FROM app.upload_quota_reservations AS r
    WHERE r.id = reservation_id
      AND r.user_id = caller
      AND r.status = 'reserved'::app.budget_reservation_status
      AND r.expires_at > timezone('utc', now())
      AND coalesce(r.cleanup_status, '') NOT IN ('pending', 'in_progress', 'done')
  );
END;
$fn$;

COMMENT ON FUNCTION app.quarantine_upload_path_allowed(text) IS
  'Storage INSERT helper: first folder = auth.uid, second = active own reservation id.';

REVOKE ALL ON FUNCTION app.quarantine_upload_path_allowed(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.quarantine_upload_path_allowed(text) TO authenticated;

-- ---------------------------------------------------------------------------
-- Storage RLS policies
-- ---------------------------------------------------------------------------

DROP POLICY IF EXISTS quarantine_authenticated_insert ON storage.objects;
CREATE POLICY quarantine_authenticated_insert
  ON storage.objects
  FOR INSERT
  TO authenticated
  WITH CHECK (
    bucket_id = 'documents-quarantine'
    AND app.quarantine_upload_path_allowed(name)
  );

-- No authenticated SELECT/UPDATE/DELETE policies on Smart RAG document
-- buckets: quarantine is non-browseable; originals/snapshots/artifacts/exports
-- remain privileged Storage Admin / worker only.

-- ---------------------------------------------------------------------------
-- Upload quota RPCs
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.reserve_upload_quota(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  declared_bytes bigint,
  idempotency_key text,
  session_id text,
  storage_path text DEFAULT NULL
)
RETURNS TABLE (
  reservation_id uuid,
  expires_at timestamptz,
  reserved_bytes bigint,
  storage_bucket text,
  reserved_storage_path text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  company_row app.company_settings%ROWTYPE;
  rolling_used bigint;
  quarantine_used bigint;
  user_cap bigint;
  company_cap bigint;
  new_id uuid;
  new_expires timestamptz;
  existing_id uuid;
  existing_expires timestamptz;
  existing_bytes bigint;
  existing_path text;
BEGIN
  IF reserve_upload_quota.declared_bytes IS NULL
    OR reserve_upload_quota.declared_bytes <= 0 THEN
    RAISE EXCEPTION 'declared_bytes must be positive';
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  SELECT * INTO profile_row
  FROM app.profiles AS p
  WHERE p.user_id = caller_user_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'profile missing';
  END IF;

  IF profile_row.role = 'viewer'::app.user_role THEN
    RAISE EXCEPTION 'viewer cannot upload';
  END IF;

  IF profile_row.role = 'member'::app.user_role THEN
    IF NOT profile_row.upload_enabled THEN
      RAISE EXCEPTION 'upload capability disabled';
    END IF;
    IF NOT profile_row.mfa_enrolled THEN
      RAISE EXCEPTION 'MFA required for upload';
    END IF;
  ELSIF profile_row.role IN ('owner'::app.user_role, 'admin'::app.user_role) THEN
    IF NOT profile_row.mfa_enrolled THEN
      RAISE EXCEPTION 'MFA required for upload';
    END IF;
  ELSE
    RAISE EXCEPTION 'role cannot upload';
  END IF;

  IF reserve_upload_quota.idempotency_key IS NOT NULL THEN
    SELECT r.id, r.expires_at, r.reserved_bytes, r.storage_path
    INTO existing_id, existing_expires, existing_bytes, existing_path
    FROM app.upload_quota_reservations AS r
    WHERE r.user_id = caller_user_id
      AND r.idempotency_key = reserve_upload_quota.idempotency_key;

    IF FOUND THEN
      reservation_id := existing_id;
      expires_at := existing_expires;
      reserved_bytes := existing_bytes;
      storage_bucket := 'documents-quarantine';
      reserved_storage_path := existing_path;
      RETURN NEXT;
      RETURN;
    END IF;
  END IF;

  SELECT * INTO company_row
  FROM app.company_settings AS cs
  WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
  FOR UPDATE;

  user_cap := coalesce(profile_row.upload_quota_bytes, company_row.upload_quota_bytes);
  company_cap := company_row.quarantine_byte_cap;

  SELECT coalesce(sum(r.reserved_bytes), 0)
  INTO rolling_used
  FROM app.upload_quota_reservations AS r
  WHERE r.user_id = caller_user_id
    AND (
      (r.status = 'reserved'::app.budget_reservation_status
        AND r.expires_at > timezone('utc', now()))
      OR (r.status = 'committed'::app.budget_reservation_status
        AND coalesce(r.cleanup_status, '') NOT IN ('done'))
    );

  IF user_cap IS NOT NULL
    AND rolling_used + reserve_upload_quota.declared_bytes > user_cap THEN
    RAISE EXCEPTION 'per-user upload quota exceeded';
  END IF;

  SELECT coalesce(sum(
    CASE
      WHEN r.actual_bytes IS NOT NULL THEN r.actual_bytes
      ELSE r.reserved_bytes
    END
  ), 0)
  INTO quarantine_used
  FROM app.upload_quota_reservations AS r
  WHERE r.status IN (
      'reserved'::app.budget_reservation_status,
      'committed'::app.budget_reservation_status
    )
    AND coalesce(r.cleanup_status, '') NOT IN ('done')
    AND (
      r.status <> 'reserved'::app.budget_reservation_status
      OR r.expires_at > timezone('utc', now())
    );

  IF company_cap IS NOT NULL
    AND quarantine_used + reserve_upload_quota.declared_bytes > company_cap THEN
    RAISE EXCEPTION 'company quarantine byte cap exceeded';
  END IF;

  new_id := gen_random_uuid();
  new_expires := timezone('utc', now()) + interval '15 minutes';

  INSERT INTO app.upload_quota_reservations (
    id,
    user_id,
    reserved_bytes,
    status,
    expires_at,
    storage_bucket,
    storage_path,
    idempotency_key,
    session_id
  )
  VALUES (
    new_id,
    caller_user_id,
    reserve_upload_quota.declared_bytes,
    'reserved'::app.budget_reservation_status,
    new_expires,
    'documents-quarantine',
    coalesce(
      reserve_upload_quota.storage_path,
      format('%s/%s/', caller_user_id::text, new_id::text)
    ),
    reserve_upload_quota.idempotency_key,
    reserve_upload_quota.session_id
  );

  reservation_id := new_id;
  expires_at := new_expires;
  reserved_bytes := reserve_upload_quota.declared_bytes;
  storage_bucket := 'documents-quarantine';
  reserved_storage_path := coalesce(
    reserve_upload_quota.storage_path,
    format('%s/%s/', caller_user_id::text, new_id::text)
  );
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.reserve_upload_quota(
  uuid, text, bigint, bigint, text, text, text
) IS
  'Atomically reserves declared upload bytes for 15 minutes; idempotent on key.';

CREATE OR REPLACE FUNCTION app.finalize_upload_quota(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_reservation_id uuid,
  actual_bytes bigint
)
RETURNS TABLE (
  reservation_id uuid,
  status app.budget_reservation_status,
  cleanup_status text,
  reserved_bytes bigint,
  recorded_actual_bytes bigint,
  over_limit boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  reservation app.upload_quota_reservations%ROWTYPE;
  company_row app.company_settings%ROWTYPE;
  company_cap bigint;
  quarantine_used bigint;
  is_over boolean := false;
BEGIN
  IF finalize_upload_quota.actual_bytes IS NULL
    OR finalize_upload_quota.actual_bytes < 0 THEN
    RAISE EXCEPTION 'actual_bytes must be non-negative';
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  SELECT * INTO reservation
  FROM app.upload_quota_reservations AS r
  WHERE r.id = p_reservation_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'reservation not found';
  END IF;

  IF reservation.user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'reservation owner mismatch';
  END IF;

  -- Idempotent finalize replay
  IF reservation.finalized_at IS NOT NULL THEN
    reservation_id := reservation.id;
    status := reservation.status;
    cleanup_status := reservation.cleanup_status;
    reserved_bytes := reservation.reserved_bytes;
    recorded_actual_bytes := reservation.actual_bytes;
    over_limit := coalesce(reservation.cleanup_status, '') = 'pending'
      AND reservation.status = 'committed'::app.budget_reservation_status;
    RETURN NEXT;
    RETURN;
  END IF;

  IF reservation.status IS DISTINCT FROM 'reserved'::app.budget_reservation_status THEN
    RAISE EXCEPTION 'reservation not active';
  END IF;

  IF reservation.expires_at <= timezone('utc', now()) THEN
    UPDATE app.upload_quota_reservations
    SET status = 'expired'::app.budget_reservation_status,
        released_at = timezone('utc', now()),
        cleanup_status = 'pending',
        actual_bytes = finalize_upload_quota.actual_bytes,
        finalized_at = timezone('utc', now()),
        updated_at = timezone('utc', now())
    WHERE id = reservation.id;

    reservation_id := reservation.id;
    status := 'expired'::app.budget_reservation_status;
    cleanup_status := 'pending';
    reserved_bytes := reservation.reserved_bytes;
    recorded_actual_bytes := finalize_upload_quota.actual_bytes;
    over_limit := true;
    RETURN NEXT;
    RETURN;
  END IF;

  SELECT * INTO company_row
  FROM app.company_settings AS cs
  WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
  FOR UPDATE;

  company_cap := company_row.quarantine_byte_cap;

  SELECT coalesce(sum(
    CASE
      WHEN r.actual_bytes IS NOT NULL THEN r.actual_bytes
      ELSE r.reserved_bytes
    END
  ), 0)
  INTO quarantine_used
  FROM app.upload_quota_reservations AS r
  WHERE r.id IS DISTINCT FROM reservation.id
    AND r.status = 'committed'::app.budget_reservation_status
    AND coalesce(r.cleanup_status, '') NOT IN ('done');

  IF finalize_upload_quota.actual_bytes > reservation.reserved_bytes THEN
    is_over := true;
  END IF;

  IF company_cap IS NOT NULL
    AND quarantine_used + finalize_upload_quota.actual_bytes > company_cap THEN
    is_over := true;
  END IF;

  UPDATE app.upload_quota_reservations AS u
  SET
    status = 'committed'::app.budget_reservation_status,
    actual_bytes = finalize_upload_quota.actual_bytes,
    finalized_at = timezone('utc', now()),
    committed_at = timezone('utc', now()),
    cleanup_status = CASE
      WHEN is_over THEN 'pending'
      ELSE u.cleanup_status
    END,
    updated_at = timezone('utc', now())
  WHERE u.id = reservation.id;

  IF is_over THEN
    PERFORM app.emit_admin_notification(
      'byte_spike',
      'warning',
      'Upload over declared or company quarantine cap',
      'Finalize marked reservation for Storage API cleanup',
      jsonb_build_object(
        'reservation_id', reservation.id,
        'user_id', caller_user_id,
        'declared_bytes', reservation.reserved_bytes,
        'actual_bytes', finalize_upload_quota.actual_bytes
      )
    );
  END IF;

  reservation_id := reservation.id;
  status := 'committed'::app.budget_reservation_status;
  cleanup_status := CASE WHEN is_over THEN 'pending' ELSE NULL END;
  reserved_bytes := reservation.reserved_bytes;
  recorded_actual_bytes := finalize_upload_quota.actual_bytes;
  over_limit := is_over;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.finalize_upload_quota(uuid, text, bigint, uuid, bigint) IS
  'Compares actual object bytes to reservation; marks over-limit for Storage cleanup.';

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
  WITH expired AS (
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
      AND r.expires_at <= as_of
    RETURNING r.id
  )
  SELECT count(*)::integer INTO released_count FROM expired;

  RETURN coalesce(released_count, 0);
END;
$fn$;

COMMENT ON FUNCTION app.release_expired_upload_reservations(timestamptz) IS
  'Idempotently expires reserved quotas past as_of and queues cleanup when needed.';

CREATE OR REPLACE FUNCTION app.list_quarantine_cleanup_candidates(
  as_of timestamptz DEFAULT timezone('utc', now()),
  result_limit integer DEFAULT 100
)
RETURNS TABLE (
  reservation_id uuid,
  user_id uuid,
  storage_bucket text,
  storage_path text,
  reserved_bytes bigint,
  actual_bytes bigint,
  cleanup_status text,
  reason text
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  ttl_hours integer;
BEGIN
  IF result_limit IS NULL OR result_limit < 1 OR result_limit > 1000 THEN
    RAISE EXCEPTION 'result_limit must be between 1 and 1000';
  END IF;

  SELECT cs.quarantine_ttl_hours
  INTO ttl_hours
  FROM app.company_settings AS cs
  WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid;

  RETURN QUERY
  SELECT
    r.id,
    r.user_id,
    coalesce(r.storage_bucket, 'documents-quarantine'),
    r.storage_path,
    r.reserved_bytes,
    r.actual_bytes,
    r.cleanup_status,
    CASE
      WHEN r.cleanup_status = 'pending'
        AND r.status = 'committed'::app.budget_reservation_status
        THEN 'over_limit'
      WHEN r.status = 'reserved'::app.budget_reservation_status
        AND r.finalized_at IS NULL
        AND r.created_at <= (as_of - make_interval(hours => coalesce(ttl_hours, 24)))
        THEN 'never_finalized'
      WHEN r.status = 'expired'::app.budget_reservation_status
        AND coalesce(r.cleanup_status, 'pending') = 'pending'
        THEN 'expired_reserved'
      ELSE 'cleanup_pending'
    END AS reason
  FROM app.upload_quota_reservations AS r
  WHERE
    (
      r.cleanup_status = 'pending'
    )
    OR (
      r.status = 'reserved'::app.budget_reservation_status
      AND r.finalized_at IS NULL
      AND r.created_at <= (as_of - make_interval(hours => coalesce(ttl_hours, 24)))
    )
  ORDER BY r.created_at ASC
  LIMIT result_limit;
END;
$fn$;

COMMENT ON FUNCTION app.list_quarantine_cleanup_candidates(timestamptz, integer) IS
  'Lists never-finalized (>TTL) or over-limit reservations for Storage API deletion.';

CREATE OR REPLACE FUNCTION app.mark_quarantine_cleanup_done(
  p_reservation_id uuid
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  UPDATE app.upload_quota_reservations
  SET
    cleanup_status = 'done',
    status = CASE
      WHEN status = 'committed'::app.budget_reservation_status
        THEN 'released'::app.budget_reservation_status
      ELSE status
    END,
    released_at = coalesce(released_at, timezone('utc', now())),
    updated_at = timezone('utc', now())
  WHERE id = p_reservation_id
    AND coalesce(cleanup_status, '') IN ('pending', 'in_progress', 'failed');
END;
$fn$;

COMMENT ON FUNCTION app.mark_quarantine_cleanup_done(uuid) IS
  'Idempotent post-Storage-API-delete reconciliation for quota rows.';

-- ---------------------------------------------------------------------------
-- Admin notifications
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.emit_admin_notification(
  kind text,
  severity text,
  title text,
  body text,
  metadata jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  IF kind IS NULL OR btrim(kind) = '' THEN
    RAISE EXCEPTION 'notification kind required';
  END IF;
  IF title IS NULL OR btrim(title) = '' THEN
    RAISE EXCEPTION 'notification title required';
  END IF;

  INSERT INTO app.admin_notifications (
    notification_kind,
    severity,
    title,
    body,
    metadata
  )
  VALUES (
    kind,
    coalesce(nullif(btrim(severity), ''), 'warning'),
    title,
    coalesce(body, ''),
    coalesce(metadata, '{}'::jsonb)
  )
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.emit_admin_notification(text, text, text, text, jsonb) IS
  'Append-only admin notification insert without raw long-retention content.';

-- Seed fixture kinds (metadata only; no secrets/content)
INSERT INTO app.admin_notifications (notification_kind, severity, title, body, metadata)
SELECT v.kind, 'info', v.title, v.body, jsonb_build_object('fixture', true, 'phase', 2)
FROM (
  VALUES
    (
      'byte_spike',
      'Fixture: upload byte spike',
      'Seeded anomaly kind for byte/rate spike detectors'
    ),
    (
      'quarantine_accumulation',
      'Fixture: quarantine accumulation',
      'Seeded anomaly kind for quarantine backlog detectors'
    ),
    (
      'repeated_scan_failure',
      'Fixture: repeated scan failure',
      'Seeded anomaly kind for scan failure detectors'
    ),
    (
      'unusual_crawl_domain',
      'Fixture: unusual crawl domain',
      'Seeded anomaly kind for crawl domain detectors'
    )
) AS v(kind, title, body)
WHERE NOT EXISTS (
  SELECT 1
  FROM app.admin_notifications AS n
  WHERE n.notification_kind = v.kind
    AND n.metadata->>'fixture' = 'true'
);

-- ---------------------------------------------------------------------------
-- Graph eligibility RPCs + ACL downgrade emits graph_acl_remove
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.emit_graph_acl_remove_for_document(p_document_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc app.documents%ROWTYPE;
BEGIN
  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = p_document_id;

  IF NOT FOUND OR doc.current_version_id IS NULL THEN
    RETURN;
  END IF;

  INSERT INTO app.lightrag_index_jobs (
    document_id,
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    doc.id,
    doc.current_version_id,
    'graph_acl_remove'::app.lightrag_job_operation,
    'high'::app.job_priority,
    format('graph_acl_remove:%s:%s', doc.id, doc.visibility_generation),
    jsonb_build_object(
      'document_id', doc.id,
      'version_id', doc.current_version_id,
      'reason', 'acl_downgrade_or_ineligible'
    )
  )
  ON CONFLICT (idempotency_key) DO NOTHING;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.bump_authorization_on_visibility_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  downgrade boolean := false;
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.visibility IS DISTINCT FROM OLD.visibility
      OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
      OR NEW.graph_eligible IS DISTINCT FROM OLD.graph_eligible THEN
      NEW.visibility_generation := OLD.visibility_generation + 1;

      IF (
        OLD.visibility = 'company_visible'::app.document_visibility
        AND NEW.visibility = 'restricted'::app.document_visibility
      )
      OR (OLD.graph_eligible = true AND NEW.graph_eligible = false)
      OR (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL) THEN
        downgrade := true;
        NEW.graph_eligible := false;
      END IF;

      UPDATE app.company_settings
      SET authorization_version = authorization_version + 1,
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
      SELECT
        NEW.current_version_id,
        CASE
          WHEN NEW.deleted_at IS NOT NULL THEN 'delete'::app.bm25_job_operation
          ELSE 'upsert'::app.bm25_job_operation
        END,
        CASE
          WHEN NEW.deleted_at IS NOT NULL OR downgrade THEN 'high'::app.job_priority
          ELSE 'normal'::app.job_priority
        END,
        format('visibility:%s:%s', NEW.id, NEW.visibility_generation),
        jsonb_build_object(
          'document_id', NEW.id,
          'reason', TG_OP,
          'visibility', NEW.visibility,
          'deleted_at', NEW.deleted_at
        )
      WHERE NEW.current_version_id IS NOT NULL
      ON CONFLICT (idempotency_key) DO NOTHING;

      IF downgrade AND NEW.current_version_id IS NOT NULL THEN
        INSERT INTO app.lightrag_index_jobs (
          document_id,
          version_id,
          operation,
          priority,
          idempotency_key,
          payload_ref
        )
        VALUES (
          NEW.id,
          NEW.current_version_id,
          'graph_acl_remove'::app.lightrag_job_operation,
          'high'::app.job_priority,
          format('graph_acl_remove:%s:%s', NEW.id, NEW.visibility_generation),
          jsonb_build_object(
            'document_id', NEW.id,
            'version_id', NEW.current_version_id,
            'reason', 'visibility_or_delete_downgrade'
          )
        )
        ON CONFLICT (idempotency_key) DO NOTHING;
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.set_document_visibility(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid,
  p_visibility app.document_visibility
)
RETURNS app.documents
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc app.documents%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'only owner/admin may change visibility';
  END IF;

  UPDATE app.documents
  SET
    visibility = p_visibility,
    graph_eligible = CASE
      WHEN p_visibility = 'restricted'::app.document_visibility THEN false
      ELSE graph_eligible
    END,
    updated_at = timezone('utc', now())
  WHERE id = p_document_id
  RETURNING * INTO doc;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'document not found';
  END IF;

  RETURN doc;
END;
$fn$;

COMMENT ON FUNCTION app.set_document_visibility(uuid, text, bigint, uuid, app.document_visibility) IS
  'Owner/admin visibility change; restricted downgrade clears graph_eligible and emits graph_acl_remove via trigger.';

CREATE OR REPLACE FUNCTION app.assert_graph_index_allowed(
  p_document_id uuid,
  p_version_id uuid DEFAULT NULL
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
  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = p_document_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'graph index rejected: document not found';
  END IF;

  IF doc.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'graph index rejected: document deleted';
  END IF;

  IF doc.visibility = 'restricted'::app.document_visibility THEN
    RAISE EXCEPTION 'graph index rejected: restricted visibility';
  END IF;

  IF doc.current_version_id IS NULL THEN
    RAISE EXCEPTION 'graph index rejected: no current version';
  END IF;

  IF p_version_id IS NOT NULL AND p_version_id IS DISTINCT FROM doc.current_version_id THEN
    RAISE EXCEPTION 'graph index rejected: non-current version';
  END IF;

  IF NOT doc.graph_eligible THEN
    RAISE EXCEPTION 'graph index rejected: not graph_eligible';
  END IF;

  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = coalesce(p_version_id, doc.current_version_id);

  IF NOT FOUND OR version_row.deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'graph index rejected: version missing or deleted';
  END IF;

  IF version_row.document_id IS DISTINCT FROM doc.id THEN
    RAISE EXCEPTION 'graph index rejected: version/document mismatch';
  END IF;

  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION app.assert_graph_index_allowed(uuid, uuid) IS
  'Fail-closed gate: only current company-visible graph_eligible versions may index.';

-- Strengthen insert trigger to also reject non-current version_id
CREATE OR REPLACE FUNCTION app.reject_restricted_graph_index_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NEW.operation IN ('index', 'rebuild') THEN
    PERFORM app.assert_graph_index_allowed(NEW.document_id, NEW.version_id);
  END IF;
  RETURN NEW;
END;
$fn$;

-- ---------------------------------------------------------------------------
-- Grants (app_api / app_worker); revoke PUBLIC
-- ---------------------------------------------------------------------------

REVOKE ALL ON FUNCTION app.reserve_upload_quota(
  uuid, text, bigint, bigint, text, text, text
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.finalize_upload_quota(
  uuid, text, bigint, uuid, bigint
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.release_expired_upload_reservations(timestamptz) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.list_quarantine_cleanup_candidates(timestamptz, integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.mark_quarantine_cleanup_done(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.emit_admin_notification(text, text, text, text, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.set_document_visibility(
  uuid, text, bigint, uuid, app.document_visibility
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.assert_graph_index_allowed(uuid, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.emit_graph_acl_remove_for_document(uuid) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.reserve_upload_quota(
  uuid, text, bigint, bigint, text, text, text
) TO app_api;
GRANT EXECUTE ON FUNCTION app.finalize_upload_quota(
  uuid, text, bigint, uuid, bigint
) TO app_api;
GRANT EXECUTE ON FUNCTION app.set_document_visibility(
  uuid, text, bigint, uuid, app.document_visibility
) TO app_api;
GRANT EXECUTE ON FUNCTION app.assert_graph_index_allowed(uuid, uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.emit_admin_notification(text, text, text, text, jsonb) TO app_api;

GRANT EXECUTE ON FUNCTION app.release_expired_upload_reservations(timestamptz) TO app_worker;
GRANT EXECUTE ON FUNCTION app.list_quarantine_cleanup_candidates(timestamptz, integer) TO app_worker;
GRANT EXECUTE ON FUNCTION app.mark_quarantine_cleanup_done(uuid) TO app_worker;
GRANT EXECUTE ON FUNCTION app.emit_admin_notification(text, text, text, text, jsonb) TO app_worker;
GRANT EXECUTE ON FUNCTION app.assert_graph_index_allowed(uuid, uuid) TO app_worker;

-- Non-clean scan foundation inserts may be recorded by API; clean requires app_worker.
GRANT SELECT, INSERT ON app.document_scan_events TO app_api;
GRANT SELECT, INSERT ON app.document_scan_events TO app_worker;
GRANT SELECT ON app.retention_holds TO app_api;
GRANT SELECT ON app.offboarding_requests TO app_api;
GRANT SELECT, INSERT, UPDATE ON app.retention_holds TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.offboarding_requests TO app_worker;
