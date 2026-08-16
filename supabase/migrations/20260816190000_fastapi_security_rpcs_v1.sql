-- Phase 6 Packet 5: FastAPI-owned conversation/run/citation/feedback/usage/
-- table-manifest/graph-entity RPCs. Expand-only SECURITY DEFINER functions
-- with fixed search_path. No DROP TABLE/COLUMN.

CREATE OR REPLACE FUNCTION app.create_conversation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_title text
)
RETURNS TABLE (
  id uuid,
  creator_user_id uuid,
  title text,
  created_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  INSERT INTO app.conversations (creator_user_id, title)
  VALUES (
    caller_user_id,
    CASE
      WHEN p_title IS NULL OR btrim(p_title) = '' THEN NULL
      ELSE left(p_title, 512)
    END
  )
  RETURNING
    app.conversations.id,
    app.conversations.creator_user_id,
    app.conversations.title,
    app.conversations.created_at
  INTO id, creator_user_id, title, created_at;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.create_conversation(uuid, text, bigint, text) IS
  'Insert one creator-owned conversation. Title is untrusted data.';

REVOKE ALL ON FUNCTION app.create_conversation(uuid, text, bigint, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.create_conversation(uuid, text, bigint, text)
  TO app_api;

CREATE OR REPLACE FUNCTION app.get_conversation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_conversation_id uuid
)
RETURNS TABLE (
  id uuid,
  creator_user_id uuid,
  title text,
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
    RAISE EXCEPTION 'conversation:authorization_rejected';
  END IF;

  RETURN QUERY
  SELECT c.id, c.creator_user_id, c.title, c.created_at
  FROM app.conversations AS c
  WHERE c.id = p_conversation_id
    AND c.deleted_at IS NULL
    AND (
      c.creator_user_id = caller_user_id
      OR caller_role IN ('owner', 'admin')
    );
END;
$fn$;

COMMENT ON FUNCTION app.get_conversation(uuid, text, bigint, uuid) IS
  'Load one non-deleted conversation. Creator or owner/admin audit read.';

REVOKE ALL ON FUNCTION app.get_conversation(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_conversation(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.get_query_run(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  id uuid,
  conversation_id uuid,
  creator_user_id uuid,
  status app.run_status,
  reservation_id uuid,
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
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  RETURN QUERY
  SELECT r.id, r.conversation_id, r.creator_user_id, r.status, r.reservation_id, r.created_at
  FROM app.runs AS r
  INNER JOIN app.conversations AS c ON c.id = r.conversation_id
  WHERE r.id = p_run_id
    AND r.creator_user_id = caller_user_id
    AND c.deleted_at IS NULL;
END;
$fn$;

COMMENT ON FUNCTION app.get_query_run(uuid, text, bigint, uuid) IS
  'Creator-only run fetch. Missing and foreign runs return no row.';

REVOKE ALL ON FUNCTION app.get_query_run(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_query_run(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.cancel_query_run(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  id uuid,
  conversation_id uuid,
  creator_user_id uuid,
  status app.run_status,
  reservation_id uuid,
  created_at timestamptz
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  IF run_row.status = 'cancelled'::app.run_status THEN
    id := run_row.id;
    conversation_id := run_row.conversation_id;
    creator_user_id := run_row.creator_user_id;
    status := run_row.status;
    reservation_id := run_row.reservation_id;
    created_at := run_row.created_at;
    RETURN NEXT;
    RETURN;
  END IF;

  IF run_row.status NOT IN (
      'pending'::app.run_status,
      'running'::app.run_status
    ) THEN
    RAISE EXCEPTION 'query_admission:run_not_cancellable';
  END IF;

  UPDATE app.runs
  SET
    status = 'cancelled'::app.run_status,
    completed_at = timezone('utc', now())
  WHERE app.runs.id = p_run_id
    AND app.runs.status IN (
      'pending'::app.run_status,
      'running'::app.run_status
    )
  RETURNING
    app.runs.id,
    app.runs.conversation_id,
    app.runs.creator_user_id,
    app.runs.status,
    app.runs.reservation_id,
    app.runs.created_at
  INTO id, conversation_id, creator_user_id, status, reservation_id, created_at;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:run_not_cancellable';
  END IF;

  IF reservation_id IS NOT NULL THEN
    PERFORM app.true_up_query_reservation_internal(reservation_id);
  END IF;

  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.cancel_query_run(uuid, text, bigint, uuid) IS
  'Creator-only cancel for pending/running query runs. True-ups the reservation. Not SSE transport.';

REVOKE ALL ON FUNCTION app.cancel_query_run(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.cancel_query_run(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.list_run_citations(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (
  citation_id uuid,
  citation_index integer,
  chunk_id uuid,
  provenance jsonb
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
    RAISE EXCEPTION 'query_admission:authorization_rejected';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.runs AS r
    INNER JOIN app.conversations AS c ON c.id = r.conversation_id
    WHERE r.id = p_run_id
      AND r.creator_user_id = caller_user_id
      AND c.deleted_at IS NULL
  ) THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  RETURN QUERY
  SELECT ct.id, ct.citation_index, ct.chunk_id, ct.provenance
  FROM app.citations AS ct
  WHERE ct.run_id = p_run_id
  ORDER BY ct.citation_index
  LIMIT 50;
END;
$fn$;

COMMENT ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid) IS
  'Creator-only citation identifiers. Snippet/passage columns are not returned.';

REVOKE ALL ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_run_citations(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.submit_run_feedback(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_rating smallint,
  p_comment text
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'feedback:authorization_rejected';
  END IF;

  IF p_rating IS NULL OR p_rating NOT IN (1, 5) THEN
    RAISE EXCEPTION 'feedback:invalid_rating';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.runs AS r
    INNER JOIN app.conversations AS c ON c.id = r.conversation_id
    WHERE r.id = p_run_id
      AND r.creator_user_id = caller_user_id
      AND c.deleted_at IS NULL
  ) THEN
    RAISE EXCEPTION 'feedback:not_found';
  END IF;

  INSERT INTO app.user_feedback (run_id, user_id, rating, comment)
  VALUES (
    p_run_id,
    caller_user_id,
    p_rating,
    CASE
      WHEN p_comment IS NULL OR btrim(p_comment) = '' THEN NULL
      ELSE left(p_comment, 2000)
    END
  )
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.submit_run_feedback(uuid, text, bigint, uuid, smallint, text) IS
  'Creator-only thumbs feedback. Rating 5=up, 1=down. Comment is untrusted.';

REVOKE ALL ON FUNCTION app.submit_run_feedback(uuid, text, bigint, uuid, smallint, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.submit_run_feedback(uuid, text, bigint, uuid, smallint, text)
  TO app_api;

CREATE OR REPLACE FUNCTION app.summarize_caller_usage(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  cost_usd numeric,
  prompt_tokens bigint,
  completion_tokens bigint,
  usage_rows bigint
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
    RAISE EXCEPTION 'usage:authorization_rejected';
  END IF;

  RETURN QUERY
  SELECT
    COALESCE(sum(u.cost_usd), 0),
    COALESCE(sum(u.prompt_tokens), 0)::bigint,
    COALESCE(sum(u.completion_tokens), 0)::bigint,
    count(*)::bigint
  FROM app.llm_usage AS u
  WHERE u.user_id = caller_user_id;
END;
$fn$;

COMMENT ON FUNCTION app.summarize_caller_usage(uuid, text, bigint) IS
  'Caller-scoped llm_usage totals. No prompt text.';

REVOKE ALL ON FUNCTION app.summarize_caller_usage(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.summarize_caller_usage(uuid, text, bigint)
  TO app_api;

CREATE OR REPLACE FUNCTION app.summarize_company_usage(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  cost_usd numeric,
  prompt_tokens bigint,
  completion_tokens bigint,
  usage_rows bigint
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
    RAISE EXCEPTION 'usage:authorization_rejected';
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'usage:forbidden';
  END IF;

  RETURN QUERY
  SELECT
    COALESCE(sum(u.cost_usd), 0),
    COALESCE(sum(u.prompt_tokens), 0)::bigint,
    COALESCE(sum(u.completion_tokens), 0)::bigint,
    count(*)::bigint
  FROM app.llm_usage AS u;
END;
$fn$;

COMMENT ON FUNCTION app.summarize_company_usage(uuid, text, bigint) IS
  'Owner/admin company llm_usage totals. No prompt text.';

REVOKE ALL ON FUNCTION app.summarize_company_usage(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.summarize_company_usage(uuid, text, bigint)
  TO app_api;

CREATE OR REPLACE FUNCTION app.list_authorized_table_manifests(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_limit integer,
  p_offset integer
)
RETURNS TABLE (
  table_id uuid,
  document_id uuid,
  version_id uuid,
  table_name text,
  sheet_name text,
  row_count integer,
  column_count integer
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  capped_limit integer;
  capped_offset integer;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'tables:authorization_rejected';
  END IF;

  capped_limit := GREATEST(1, LEAST(COALESCE(p_limit, 50), 50));
  capped_offset := GREATEST(0, LEAST(COALESCE(p_offset, 0), 10000));

  RETURN QUERY
  SELECT
    dt.id,
    dt.document_id,
    dt.version_id,
    dt.table_name,
    dt.sheet_name,
    dt.row_count,
    dt.column_count
  FROM app.document_tables AS dt
  INNER JOIN app.documents AS d ON d.id = dt.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = dt.version_id
  WHERE d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM dt.version_id
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ORDER BY dt.id
  LIMIT capped_limit
  OFFSET capped_offset;
END;
$fn$;

COMMENT ON FUNCTION app.list_authorized_table_manifests(uuid, text, bigint, integer, integer) IS
  'ACL-filtered current-version table manifests. No Parquet paths.';

REVOKE ALL ON FUNCTION app.list_authorized_table_manifests(uuid, text, bigint, integer, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_authorized_table_manifests(uuid, text, bigint, integer, integer)
  TO app_api;

CREATE OR REPLACE FUNCTION app.get_visible_document(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid
)
RETURNS TABLE (
  id uuid,
  title text,
  visibility app.document_visibility,
  current_version_id uuid,
  visibility_generation bigint
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
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;

  RETURN QUERY
  SELECT
    d.id,
    d.title,
    d.visibility,
    d.current_version_id,
    d.visibility_generation
  FROM app.documents AS d
  WHERE d.id = p_document_id
    AND d.deleted_at IS NULL
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id);
END;
$fn$;

COMMENT ON FUNCTION app.get_visible_document(uuid, text, bigint, uuid) IS
  'One ACL-visible non-deleted document. Unauthorized ids return no row.';

REVOKE ALL ON FUNCTION app.get_visible_document(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_visible_document(uuid, text, bigint, uuid)
  TO app_api;

CREATE OR REPLACE FUNCTION app.search_graph_entities(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_query text,
  p_limit integer
)
RETURNS TABLE (
  object_id text,
  object_type text,
  chunk_id uuid,
  document_id uuid,
  version_id uuid,
  support numeric
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  capped_limit integer;
  needle text;
BEGIN
  PERFORM set_config('statement_timeout', '3s', true);

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'graph:authorization_rejected';
  END IF;

  IF p_query IS NULL OR btrim(p_query) = '' OR char_length(p_query) > 64 THEN
    RAISE EXCEPTION 'graph:invalid_query';
  END IF;

  capped_limit := GREATEST(1, LEAST(COALESCE(p_limit, 25), 25));
  needle := '%' || replace(replace(btrim(p_query), '%', ''), '_', '') || '%';

  RETURN QUERY
  SELECT
    gem.graph_object_id,
    gem.graph_object_type,
    gem.chunk_id,
    c.document_id,
    gem.version_id,
    gem.support
  FROM app.graph_evidence_map AS gem
  INNER JOIN app.document_chunks AS c ON c.id = gem.chunk_id
  INNER JOIN app.documents AS d ON d.id = c.document_id
  INNER JOIN app.document_versions AS dv ON dv.id = c.version_id
  WHERE gem.graph_object_type = 'entity'
    AND gem.support >= 0.80
    AND gem.pipeline_version = 'graph_pipeline_v1'
    AND c.deleted_at IS NULL
    AND d.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND d.current_version_id IS NOT DISTINCT FROM c.version_id
    AND dv.status = 'graph_ready'::app.document_status
    AND d.graph_eligible IS TRUE
    AND dv.graph_eligible IS TRUE
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
    AND gem.graph_object_id ILIKE needle
  ORDER BY gem.support DESC, gem.graph_object_id
  LIMIT capped_limit;
END;
$fn$;

COMMENT ON FUNCTION app.search_graph_entities(uuid, text, bigint, text, integer) IS
  'Bounded ACL-filtered entity id search. No vendor prose.';

REVOKE ALL ON FUNCTION app.search_graph_entities(uuid, text, bigint, text, integer)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.search_graph_entities(uuid, text, bigint, text, integer)
  TO app_api;

CREATE OR REPLACE FUNCTION app.upsert_tool_catalog_seed(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_tool_key text,
  p_display_name text,
  p_description text,
  p_active boolean
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  new_id uuid;
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

  IF p_tool_key IS NULL OR btrim(p_tool_key) = '' OR char_length(p_tool_key) > 64 THEN
    RAISE EXCEPTION 'tools:invalid_key';
  END IF;

  INSERT INTO app.tool_catalog (tool_key, display_name, description, active)
  VALUES (
    btrim(p_tool_key),
    left(COALESCE(p_display_name, p_tool_key), 128),
    left(COALESCE(p_description, ''), 512),
    COALESCE(p_active, false)
  )
  ON CONFLICT (tool_key) DO UPDATE
    SET
      display_name = EXCLUDED.display_name,
      description = EXCLUDED.description,
      active = EXCLUDED.active
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.upsert_tool_catalog_seed(uuid, text, bigint, text, text, text, boolean) IS
  'Owner/admin catalog seed. Runtime authorization remains the in-code registry plus live role.';

REVOKE ALL ON FUNCTION app.upsert_tool_catalog_seed(uuid, text, bigint, text, text, text, boolean)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.upsert_tool_catalog_seed(uuid, text, bigint, text, text, text, boolean)
  TO app_api;

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

  SELECT tc.id INTO catalog_id
  FROM app.tool_catalog AS tc
  WHERE tc.tool_key = btrim(p_tool_key);

  IF catalog_id IS NULL THEN
    RAISE EXCEPTION 'tools:not_found';
  END IF;

  INSERT INTO app.tool_permissions (tool_id, role, permission)
  VALUES (catalog_id, p_target_role, p_permission)
  RETURNING id INTO perm_id;

  RETURN perm_id;
END;
$fn$;

COMMENT ON FUNCTION app.set_tool_permission(uuid, text, bigint, text, app.user_role, app.tool_permission_level) IS
  'Owner/admin tool permission seed. Executor still rechecks live role against the in-code registry.';

REVOKE ALL ON FUNCTION app.set_tool_permission(
  uuid, text, bigint, text, app.user_role, app.tool_permission_level
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.set_tool_permission(
  uuid, text, bigint, text, app.user_role, app.tool_permission_level
) TO app_api;
