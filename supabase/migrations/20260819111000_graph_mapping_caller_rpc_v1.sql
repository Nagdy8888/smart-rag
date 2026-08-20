-- Narrow worker identity lookup for bounded graph mapping support.

CREATE OR REPLACE FUNCTION app.load_graph_mapping_caller(
  p_version_id uuid
)
RETURNS TABLE (
  user_id uuid,
  role app.user_role,
  authorization_version bigint,
  disabled_at timestamptz,
  upload_enabled boolean,
  mfa_enrolled boolean
)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
  SELECT
    p.user_id,
    p.role,
    cs.authorization_version,
    p.disabled_at,
    p.upload_enabled,
    p.mfa_enrolled
  FROM app.document_versions AS dv
  JOIN app.documents AS d ON d.id = dv.document_id
  JOIN app.profiles AS p ON p.user_id = d.created_by
  JOIN app.company_settings AS cs
    ON cs.id = '00000000-0000-0000-0000-000000000001'::uuid
  WHERE dv.id = p_version_id
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL;
$fn$;

REVOKE ALL ON FUNCTION app.load_graph_mapping_caller(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.load_graph_mapping_caller(uuid) FROM anon;
REVOKE ALL ON FUNCTION app.load_graph_mapping_caller(uuid) FROM authenticated;
REVOKE ALL ON FUNCTION app.load_graph_mapping_caller(uuid) FROM app_api;
GRANT EXECUTE ON FUNCTION app.load_graph_mapping_caller(uuid) TO app_worker;

COMMENT ON FUNCTION app.load_graph_mapping_caller(uuid) IS
  'Returns only the uploader authorization fields needed by version-scoped graph mapping support; app_worker receives EXECUTE, not profiles table access.';
