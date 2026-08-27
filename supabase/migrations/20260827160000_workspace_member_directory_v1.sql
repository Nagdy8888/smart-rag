-- Owner/admin workspace member and pending-invitation listing.
-- Bounded, no invitation token_hash, EXECUTE to app_api only.

CREATE OR REPLACE FUNCTION app.list_workspace_members(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  user_id uuid,
  email text,
  display_name text,
  role app.user_role,
  upload_enabled boolean,
  disabled_at timestamptz,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'team:authorization_rejected';
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'team:forbidden';
  END IF;

  RETURN QUERY
  SELECT
    p.user_id,
    COALESCE(u.email::text, ''),
    p.display_name,
    p.role,
    p.upload_enabled,
    p.disabled_at,
    p.created_at
  FROM app.profiles AS p
  LEFT JOIN auth.users AS u ON u.id = p.user_id
  ORDER BY p.created_at ASC, p.user_id ASC
  LIMIT 200;
END;
$fn$;

COMMENT ON FUNCTION app.list_workspace_members(uuid, text, bigint) IS
  'Owner/admin workspace membership. Emails from auth.users. No tokens. Max 200.';

REVOKE ALL ON FUNCTION app.list_workspace_members(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_workspace_members(uuid, text, bigint)
  TO app_api;

CREATE OR REPLACE FUNCTION app.list_pending_team_invitations(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  invitation_id uuid,
  email text,
  role app.user_role,
  upload_enabled boolean,
  expires_at timestamptz,
  created_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'team:authorization_rejected';
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'team:forbidden';
  END IF;

  RETURN QUERY
  SELECT
    inv.id,
    inv.email,
    inv.role,
    inv.upload_enabled,
    inv.expires_at,
    inv.created_at
  FROM app.team_invitations AS inv
  WHERE inv.accepted_at IS NULL
    AND inv.revoked_at IS NULL
  ORDER BY inv.created_at DESC, inv.id DESC
  LIMIT 200;
END;
$fn$;

COMMENT ON FUNCTION app.list_pending_team_invitations(uuid, text, bigint) IS
  'Owner/admin unaccepted invitations. Never returns token_hash. Max 200.';

REVOKE ALL ON FUNCTION app.list_pending_team_invitations(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_pending_team_invitations(uuid, text, bigint)
  TO app_api;
