-- Admin catalog overlay: unique role permissions, missing-catalog insert,
-- and a seed listing RPC so GET /tools can show enable/disable writes.

DELETE FROM app.tool_permissions AS tp
WHERE tp.user_id IS NULL
  AND tp.role IS NOT NULL
  AND tp.id NOT IN (
    SELECT kept.id
    FROM (
      SELECT DISTINCT ON (tool_id, role) id
      FROM app.tool_permissions
      WHERE user_id IS NULL
        AND role IS NOT NULL
      ORDER BY tool_id, role, updated_at DESC, created_at DESC, id DESC
    ) AS kept
  );

CREATE UNIQUE INDEX IF NOT EXISTS tool_permissions_tool_role_uq
  ON app.tool_permissions (tool_id, role)
  WHERE user_id IS NULL AND role IS NOT NULL;

CREATE OR REPLACE FUNCTION app.set_tool_permission(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_tool_key text,
  p_target_role app.user_role,
  p_permission app.tool_permission_level
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  catalog_id uuid;
  perm_id uuid;
  trimmed_key text;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'tools:authorization_rejected';
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'tools:forbidden';
  END IF;

  trimmed_key := btrim(p_tool_key);
  IF trimmed_key IS NULL OR trimmed_key = '' OR char_length(trimmed_key) > 64 THEN
    RAISE EXCEPTION 'tools:invalid_key';
  END IF;

  SELECT tc.id INTO catalog_id
  FROM app.tool_catalog AS tc
  WHERE tc.tool_key = trimmed_key;

  IF catalog_id IS NULL THEN
    INSERT INTO app.tool_catalog (tool_key, display_name, description, active)
    VALUES (trimmed_key, left(trimmed_key, 128), '', true)
    RETURNING id INTO catalog_id;
  END IF;

  INSERT INTO app.tool_permissions (tool_id, role, permission)
  VALUES (catalog_id, p_target_role, p_permission)
  ON CONFLICT (tool_id, role) WHERE user_id IS NULL AND role IS NOT NULL
  DO UPDATE SET permission = EXCLUDED.permission
  RETURNING id INTO perm_id;

  RETURN perm_id;
END;
$fn$;

COMMENT ON FUNCTION app.set_tool_permission(
  uuid, text, bigint, text, app.user_role, app.tool_permission_level
) IS
  'Owner/admin tool permission upsert by tool_key and role. Creates a catalog row when missing. Executor still rechecks the in-code registry.';

CREATE OR REPLACE FUNCTION app.list_tool_catalog_seeds(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  tool_key text,
  active boolean
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
    RAISE EXCEPTION 'tools:authorization_rejected';
  END IF;

  RETURN QUERY
  SELECT tc.tool_key, tc.active
  FROM app.tool_catalog AS tc;
END;
$fn$;

COMMENT ON FUNCTION app.list_tool_catalog_seeds(uuid, text, bigint) IS
  'Catalog seed active flags for overlay onto GET /tools. HTTP never returns keys the live role cannot already see from the in-code registry.';

REVOKE ALL ON FUNCTION app.list_tool_catalog_seeds(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_tool_catalog_seeds(uuid, text, bigint)
  TO app_api;
