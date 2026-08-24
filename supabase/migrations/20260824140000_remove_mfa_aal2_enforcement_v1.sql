-- P08-11: remove live MFA/AAL2 authorization gates.
-- Additive only. Historical migrations remain immutable. Function signatures are preserved.

COMMENT ON COLUMN app.profiles.mfa_enrolled IS
  'Deprecated compatibility flag. No live authorization decision reads this column.';

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
  reserved_storage_path text,
  document_id uuid,
  version_id uuid
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
  existing_document_id uuid;
  existing_version_id uuid;
  new_document_id uuid;
  new_version_id uuid;
  reserved_path text;
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
  ELSIF profile_row.role IN ('owner'::app.user_role, 'admin'::app.user_role) THEN
  ELSE
    RAISE EXCEPTION 'role cannot upload';
  END IF;

  IF reserve_upload_quota.idempotency_key IS NOT NULL THEN
    SELECT r.id, r.expires_at, r.reserved_bytes, r.storage_path, r.document_id, r.version_id
    INTO existing_id, existing_expires, existing_bytes, existing_path,
         existing_document_id, existing_version_id
    FROM app.upload_quota_reservations AS r
    WHERE r.user_id = caller_user_id
      AND r.idempotency_key = reserve_upload_quota.idempotency_key;

    IF FOUND THEN
      reservation_id := existing_id;
      expires_at := existing_expires;
      reserved_bytes := existing_bytes;
      storage_bucket := 'documents-quarantine';
      reserved_storage_path := existing_path;
      document_id := existing_document_id;
      version_id := existing_version_id;
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
  reserved_path := coalesce(
    reserve_upload_quota.storage_path,
    format('%s/%s/', caller_user_id::text, new_id::text)
  );

  INSERT INTO app.documents (title, created_by)
  VALUES ('Uploading', caller_user_id)
  RETURNING id INTO new_document_id;

  INSERT INTO app.document_versions (
    document_id,
    version_number,
    status,
    created_by
  )
  VALUES (
    new_document_id,
    1,
    'uploading'::app.document_status,
    caller_user_id
  )
  RETURNING id INTO new_version_id;

  UPDATE app.documents
  SET current_version_id = new_version_id, updated_at = timezone('utc', now())
  WHERE id = new_document_id;

  INSERT INTO app.upload_quota_reservations (
    id,
    user_id,
    reserved_bytes,
    status,
    expires_at,
    storage_bucket,
    storage_path,
    idempotency_key,
    session_id,
    document_id,
    version_id
  )
  VALUES (
    new_id,
    caller_user_id,
    reserve_upload_quota.declared_bytes,
    'reserved'::app.budget_reservation_status,
    new_expires,
    'documents-quarantine',
    reserved_path,
    reserve_upload_quota.idempotency_key,
    reserve_upload_quota.session_id,
    new_document_id,
    new_version_id
  );

  reservation_id := new_id;
  expires_at := new_expires;
  reserved_bytes := reserve_upload_quota.declared_bytes;
  storage_bucket := 'documents-quarantine';
  reserved_storage_path := reserved_path;
  document_id := new_document_id;
  version_id := new_version_id;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.reserve_upload_quota(
  uuid, text, bigint, bigint, text, text, text
) IS
  'Reserves declared upload bytes for 15 minutes and creates an uploading version. MFA enrollment is not an authorization gate.';

REVOKE ALL ON FUNCTION app.reserve_upload_quota(
  uuid, text, bigint, bigint, text, text, text
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.reserve_upload_quota(
  uuid, text, bigint, bigint, text, text, text
) TO app_api;

CREATE OR REPLACE FUNCTION app.accept_invitation(
  p_token_hash text,
  p_user_id uuid,
  p_user_email text,
  p_assurance_level text DEFAULT 'aal1'
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  invitation app.team_invitations%ROWTYPE;
  existing_role app.user_role;
  existing_upload boolean;
  invite_rank integer;
  existing_rank integer;
  privileged_change boolean := false;
  upload_change boolean := false;
BEGIN
  -- p_assurance_level is a deprecated compatibility argument and is ignored.
  IF p_token_hash IS NULL OR btrim(p_token_hash) = '' OR p_user_id IS NULL THEN
    RAISE EXCEPTION 'invalid invitation accept arguments';
  END IF;

  SELECT *
  INTO invitation
  FROM app.team_invitations AS ti
  WHERE ti.token_hash = p_token_hash
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'invitation not found';
  END IF;

  IF invitation.revoked_at IS NOT NULL THEN
    RAISE EXCEPTION 'invitation revoked';
  END IF;

  IF invitation.expires_at <= timezone('utc', now()) THEN
    RAISE EXCEPTION 'invitation expired';
  END IF;

  IF lower(btrim(p_user_email)) <> invitation.email THEN
    RAISE EXCEPTION 'invitation email mismatch';
  END IF;

  IF invitation.accepted_at IS NOT NULL THEN
    IF invitation.accepted_by = p_user_id THEN
      RETURN invitation.id;
    END IF;
    RAISE EXCEPTION 'invitation already accepted';
  END IF;

  invite_rank := CASE invitation.role
    WHEN 'viewer'::app.user_role THEN 0
    WHEN 'member'::app.user_role THEN 1
    WHEN 'admin'::app.user_role THEN 2
    WHEN 'owner'::app.user_role THEN 3
    ELSE -1
  END;

  SELECT p.role, p.upload_enabled
  INTO existing_role, existing_upload
  FROM app.profiles AS p
  WHERE p.user_id = p_user_id
  FOR UPDATE;

  IF FOUND THEN
    existing_rank := CASE existing_role
      WHEN 'viewer'::app.user_role THEN 0
      WHEN 'member'::app.user_role THEN 1
      WHEN 'admin'::app.user_role THEN 2
      WHEN 'owner'::app.user_role THEN 3
      ELSE -1
    END;

    IF invite_rank < existing_rank THEN
      RAISE EXCEPTION 'invitation would demote existing profile';
    END IF;

    IF invitation.upload_enabled IS FALSE AND existing_upload IS TRUE THEN
      RAISE EXCEPTION 'invitation would demote existing profile';
    END IF;

    privileged_change := invite_rank > existing_rank;
    upload_change := invitation.upload_enabled IS TRUE AND existing_upload IS FALSE;

    UPDATE app.profiles
    SET
      role = CASE
        WHEN invite_rank > existing_rank THEN invitation.role
        ELSE existing_role
      END,
      upload_enabled = (existing_upload OR invitation.upload_enabled)
    WHERE user_id = p_user_id;

    IF privileged_change OR upload_change THEN
      PERFORM app.revoke_session(
        format('invitation-accept:%s', invitation.id),
        p_user_id
      );
    END IF;
  ELSE
    INSERT INTO app.profiles (user_id, role, upload_enabled)
    VALUES (p_user_id, invitation.role, invitation.upload_enabled);
  END IF;

  UPDATE app.team_invitations
  SET
    accepted_at = timezone('utc', now()),
    accepted_by = p_user_id
  WHERE id = invitation.id;

  PERFORM app.append_audit_event(
    'invitation.accepted',
    p_user_id,
    invitation.role,
    'team_invitation',
    invitation.id,
    app.current_authorization_version(),
    jsonb_build_object('email', invitation.email)
  );

  RETURN invitation.id;
END;
$fn$;

COMMENT ON FUNCTION app.accept_invitation(text, uuid, text, text) IS
  'Idempotent invitation acceptance. Refuses demotion; privileged/upload upgrades revoke sessions. p_assurance_level is retained and ignored.';

REVOKE ALL ON FUNCTION app.accept_invitation(text, uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.accept_invitation(text, uuid, text, text) TO app_api;
