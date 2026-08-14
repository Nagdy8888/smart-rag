-- Phase 4 Packet 7: authorized structured-table resolver.
-- Expand/contract: CREATE OR REPLACE FUNCTION plus REVOKE/GRANT. No DROP TABLE.

CREATE OR REPLACE FUNCTION app.resolve_structured_table(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_table_id uuid,
  p_version_id uuid
)
RETURNS TABLE (
  table_id uuid,
  document_id uuid,
  version_id uuid,
  table_name text,
  sheet_name text,
  parquet_bucket text,
  parquet_path text,
  row_count integer,
  column_count integer,
  provenance jsonb
)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app, extensions, search
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  RETURN QUERY
  SELECT
    dt.id,
    dt.document_id,
    dt.version_id,
    dt.table_name,
    dt.sheet_name,
    dt.parquet_bucket,
    dt.parquet_path,
    dt.row_count,
    dt.column_count,
    dt.provenance
  FROM app.document_tables AS dt
  INNER JOIN app.documents AS d ON d.id = dt.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = dt.version_id
  WHERE dt.id = p_table_id
    AND dt.version_id = p_version_id
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM dt.version_id
    AND dv.status IN (
      'hybrid_ready'::app.document_status,
      'graph_pending'::app.document_status,
      'graph_ready'::app.document_status,
      'graph_ineligible'::app.document_status
    )
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id);
END;
$fn$;

COMMENT ON FUNCTION app.resolve_structured_table(uuid, text, bigint, uuid, uuid) IS
  'Returns one current ACL-visible table artifact. Client/model paths never participate.';

REVOKE ALL ON FUNCTION app.resolve_structured_table(uuid, text, bigint, uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.resolve_structured_table(uuid, text, bigint, uuid, uuid) TO app_api;
