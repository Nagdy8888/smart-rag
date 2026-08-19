-- PRD-H-025: Invitation accept must not demote an existing profile.
-- Monotonic role/upload upgrades require AAL2 and revoke sessions.

DROP FUNCTION IF EXISTS app.accept_invitation(text, uuid, text);

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

    IF (privileged_change OR upload_change)
      AND coalesce(p_assurance_level, 'aal1') NOT IN ('aal2', 'aal3')
    THEN
      RAISE EXCEPTION 'invitation privileged upgrade requires aal2';
    END IF;

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
    IF invitation.role IN ('owner'::app.user_role, 'admin'::app.user_role)
      AND coalesce(p_assurance_level, 'aal1') NOT IN ('aal2', 'aal3')
    THEN
      RAISE EXCEPTION 'invitation privileged upgrade requires aal2';
    END IF;

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
  'Idempotent invitation acceptance. Refuses demotion; privileged/upload upgrades require AAL2 and revoke sessions.';

REVOKE ALL ON FUNCTION app.accept_invitation(text, uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.accept_invitation(text, uuid, text, text) TO app_api;
