-- Phase 2 Packet 4: invitation columns, revoked sessions, MFA recovery, auth RPCs, rate limits.

ALTER TABLE app.team_invitations
  ADD COLUMN IF NOT EXISTS upload_enabled boolean NOT NULL DEFAULT false;

ALTER TABLE app.team_invitations
  ADD COLUMN IF NOT EXISTS accepted_by uuid REFERENCES auth.users (id) ON DELETE SET NULL;

COMMENT ON COLUMN app.team_invitations.upload_enabled IS
  'Whether the invited member receives upload capability after acceptance.';

COMMENT ON COLUMN app.team_invitations.accepted_by IS
  'Authenticated user who accepted the invitation; set once on successful accept.';

CREATE TABLE app.revoked_sessions (
  session_id text PRIMARY KEY,
  user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  revoked_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE app.revoked_sessions IS
  'Explicit refresh-session identifiers revoked before access-token expiry.';

CREATE TABLE app.mfa_recovery_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subject_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  initiated_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'initiated',
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT mfa_recovery_requests_status_check CHECK (
    status IN ('initiated', 'completed', 'cancelled')
  )
);

COMMENT ON TABLE app.mfa_recovery_requests IS
  'Audited lost-factor recovery workflow; completion requires privileged Auth Admin.';

CREATE INDEX mfa_recovery_requests_subject_idx
  ON app.mfa_recovery_requests (subject_user_id, created_at DESC);

-- ---------------------------------------------------------------------------
-- Postgres degraded auth rate-limit bucket (FastAPI-owned writes only)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION private.consume_auth_rate_limit(
  p_bucket_key text,
  p_max_attempts integer,
  p_window_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $fn$
DECLARE
  v_window_start timestamptz;
  current_count integer;
BEGIN
  IF p_bucket_key IS NULL OR btrim(p_bucket_key) = '' THEN
    RETURN false;
  END IF;

  IF p_max_attempts IS NULL OR p_max_attempts < 1 THEN
    RETURN false;
  END IF;

  IF p_window_seconds IS NULL OR p_window_seconds < 1 THEN
    RETURN false;
  END IF;

  v_window_start :=
    to_timestamp(
      floor(
        extract(epoch FROM timezone('utc', now())) / p_window_seconds
      ) * p_window_seconds
    );

  INSERT INTO private.auth_rate_limit_buckets AS b (
    bucket_key,
    window_start,
    attempt_count
  )
  VALUES (p_bucket_key, v_window_start, 1)
  ON CONFLICT (bucket_key, window_start)
  DO UPDATE
    SET
      attempt_count = b.attempt_count + 1,
      updated_at = timezone('utc', now())
  RETURNING attempt_count INTO current_count;

  RETURN current_count <= p_max_attempts;
END;
$fn$;

COMMENT ON FUNCTION private.consume_auth_rate_limit(text, integer, integer) IS
  'Atomic degraded rate-limit counter. Returns false when the window is exhausted.';

REVOKE ALL ON FUNCTION private.consume_auth_rate_limit(text, integer, integer) FROM PUBLIC;
GRANT USAGE ON SCHEMA private TO app_api;
GRANT EXECUTE ON FUNCTION private.consume_auth_rate_limit(text, integer, integer) TO app_api;

-- ---------------------------------------------------------------------------
-- One-time owner bootstrap (race-safe)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.bootstrap_owner(p_user_id uuid)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  owner_exists boolean;
  assigned_role app.user_role;
BEGIN
  IF p_user_id IS NULL THEN
    RETURN false;
  END IF;

  PERFORM pg_advisory_xact_lock(hashtext('app.bootstrap_owner'));

  SELECT EXISTS (
    SELECT 1
    FROM app.profiles AS p
    WHERE p.role = 'owner'::app.user_role
      AND p.disabled_at IS NULL
  )
  INTO owner_exists;

  IF owner_exists THEN
    RETURN false;
  END IF;

  INSERT INTO app.profiles (user_id, role, display_name)
  VALUES (p_user_id, 'owner', NULL)
  ON CONFLICT (user_id) DO UPDATE
    SET role = 'owner'::app.user_role
  RETURNING role INTO assigned_role;

  IF assigned_role IS DISTINCT FROM 'owner'::app.user_role THEN
    RETURN false;
  END IF;

  PERFORM app.append_audit_event(
    'owner.bootstrap',
    p_user_id,
    'owner'::app.user_role,
    'company',
    '00000000-0000-0000-0000-000000000001'::uuid,
    app.current_authorization_version(),
    jsonb_build_object('bootstrap', true)
  );

  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION app.bootstrap_owner(uuid) IS
  'Race-safe one-time owner bootstrap when no active owner profile exists.';

REVOKE ALL ON FUNCTION app.bootstrap_owner(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.bootstrap_owner(uuid) TO app_api;

-- ---------------------------------------------------------------------------
-- Invitation acceptance (idempotent, single-use, 24h expiry enforced upstream)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.accept_invitation(
  p_token_hash text,
  p_user_id uuid,
  p_user_email text
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  invitation app.team_invitations%ROWTYPE;
  invitation_id uuid;
BEGIN
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

  UPDATE app.team_invitations
  SET
    accepted_at = timezone('utc', now()),
    accepted_by = p_user_id
  WHERE id = invitation.id;

  INSERT INTO app.profiles (user_id, role, upload_enabled)
  VALUES (p_user_id, invitation.role, invitation.upload_enabled)
  ON CONFLICT (user_id) DO UPDATE
    SET
      role = EXCLUDED.role,
      upload_enabled = EXCLUDED.upload_enabled;

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

COMMENT ON FUNCTION app.accept_invitation(text, uuid, text) IS
  'Idempotent invitation acceptance keyed by token_hash; rejects replay and expiry.';

REVOKE ALL ON FUNCTION app.accept_invitation(text, uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.accept_invitation(text, uuid, text) TO app_api;

-- ---------------------------------------------------------------------------
-- Session revocation helper (privileged workflows)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.revoke_session(
  p_session_id text,
  p_user_id uuid
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF p_session_id IS NULL OR btrim(p_session_id) = '' OR p_user_id IS NULL THEN
    RETURN false;
  END IF;

  INSERT INTO app.revoked_sessions (session_id, user_id)
  VALUES (p_session_id, p_user_id)
  ON CONFLICT (session_id) DO NOTHING;

  UPDATE app.profiles
  SET session_revoked_at = timezone('utc', now())
  WHERE user_id = p_user_id;

  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION app.revoke_session(text, uuid) IS
  'Record one revoked refresh session and bump profile session_revoked_at.';

REVOKE ALL ON FUNCTION app.revoke_session(text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.revoke_session(text, uuid) TO app_api;

GRANT SELECT ON app.revoked_sessions TO app_api;
GRANT SELECT, INSERT, UPDATE ON app.team_invitations TO app_api;
GRANT SELECT, INSERT, UPDATE ON app.mfa_recovery_requests TO app_api;
