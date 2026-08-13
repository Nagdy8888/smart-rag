-- Phase 2 Packet 3 remediation: typed, transaction-pool-safe ACL mutation.

CREATE OR REPLACE FUNCTION private.set_document_acl(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid,
  p_grantee_user_id uuid,
  p_grant boolean
)
RETURNS boolean
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $fn$
DECLARE
  target_visibility app.document_visibility;
  target_deleted_at timestamptz;
  grantee_disabled_at timestamptz;
  active_grant_exists boolean;
  changed_rows integer;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'only owner/admin may change document ACL';
  END IF;

  IF p_document_id IS NULL OR p_grantee_user_id IS NULL OR p_grant IS NULL THEN
    RAISE EXCEPTION 'document, grantee, and grant decision are required';
  END IF;

  SELECT d.visibility, d.deleted_at
  INTO target_visibility, target_deleted_at
  FROM app.documents AS d
  WHERE d.id = p_document_id
  FOR UPDATE;

  IF NOT FOUND OR target_deleted_at IS NOT NULL THEN
    RAISE EXCEPTION 'active document not found';
  END IF;

  SELECT p.disabled_at
  INTO grantee_disabled_at
  FROM app.profiles AS p
  WHERE p.user_id = p_grantee_user_id;

  IF NOT FOUND OR grantee_disabled_at IS NOT NULL THEN
    RAISE EXCEPTION 'active grantee profile not found';
  END IF;

  IF p_grant THEN
    IF target_visibility IS DISTINCT FROM 'restricted'::app.document_visibility THEN
      RAISE EXCEPTION 'explicit ACL grants require restricted visibility';
    END IF;

    SELECT EXISTS (
      SELECT 1
      FROM app.document_acl AS acl
      WHERE acl.document_id = p_document_id
        AND acl.grantee_user_id = p_grantee_user_id
        AND acl.revoked_at IS NULL
    )
    INTO active_grant_exists;

    IF active_grant_exists THEN
      RETURN false;
    END IF;

    INSERT INTO app.document_acl (
      document_id,
      grantee_user_id,
      granted_by
    )
    VALUES (
      p_document_id,
      p_grantee_user_id,
      caller_user_id
    );
  ELSE
    UPDATE app.document_acl AS acl
    SET
      revoked_at = timezone('utc', now()),
      updated_at = timezone('utc', now())
    WHERE acl.document_id = p_document_id
      AND acl.grantee_user_id = p_grantee_user_id
      AND acl.revoked_at IS NULL;

    GET DIAGNOSTICS changed_rows = ROW_COUNT;
    IF changed_rows = 0 THEN
      RETURN false;
    END IF;
  END IF;

  PERFORM app.append_audit_event(
    CASE
      WHEN p_grant THEN 'document_acl.granted'
      ELSE 'document_acl.revoked'
    END,
    caller_user_id,
    caller_role::app.user_role,
    'document',
    p_document_id,
    app.current_authorization_version(),
    jsonb_build_object(
      'grantee_user_id', p_grantee_user_id,
      'action', CASE WHEN p_grant THEN 'grant' ELSE 'revoke' END
    )
  );

  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION private.set_document_acl(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  boolean
) IS
  'Owner/admin ACL mutation using explicit server-derived context; idempotent per active grant.';

REVOKE ALL ON FUNCTION private.set_document_acl(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  boolean
) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.set_document_acl(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  boolean
) FROM anon, authenticated;

GRANT USAGE ON SCHEMA private TO app_api;
GRANT EXECUTE ON FUNCTION private.set_document_acl(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  boolean
) TO app_api;
