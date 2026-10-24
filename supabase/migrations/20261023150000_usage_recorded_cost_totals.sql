-- Sum recorded usage costs rather than repricing every model as gpt-4o-mini.
-- Preserve existing authorization checks and RPC return contracts.

CREATE OR REPLACE FUNCTION app.summarize_run_usage(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid
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
  SELECT
    COALESCE(
      sum(u.cost_usd),
      0
    ),
    COALESCE(sum(u.prompt_tokens), 0)::bigint,
    COALESCE(sum(u.completion_tokens), 0)::bigint,
    count(u.id)::bigint
  FROM app.llm_usage AS u
  WHERE u.run_id = p_run_id;
END;
$fn$;

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
    COALESCE(
      sum(u.cost_usd),
      0
    ),
    COALESCE(sum(u.prompt_tokens), 0)::bigint,
    COALESCE(sum(u.completion_tokens), 0)::bigint,
    count(*)::bigint
  FROM app.llm_usage AS u
  WHERE u.user_id = caller_user_id;
END;
$fn$;

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
    COALESCE(
      sum(u.cost_usd),
      0
    ),
    COALESCE(sum(u.prompt_tokens), 0)::bigint,
    COALESCE(sum(u.completion_tokens), 0)::bigint,
    count(*)::bigint
  FROM app.llm_usage AS u;
END;
$fn$;

COMMENT ON FUNCTION app.summarize_run_usage(uuid, text, bigint, uuid) IS
  'Creator-only recorded usage totals for one owned query run. USD is the recorded application cost estimate; not a provider invoice.';

COMMENT ON FUNCTION app.summarize_caller_usage(uuid, text, bigint) IS
  'Caller-scoped llm_usage totals. USD is the recorded application cost estimate; not a provider invoice.';

COMMENT ON FUNCTION app.summarize_company_usage(uuid, text, bigint) IS
  'Owner/admin company llm_usage totals. USD is the recorded application cost estimate; not a provider invoice.';

REVOKE ALL ON FUNCTION app.summarize_run_usage(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.summarize_run_usage(uuid, text, bigint, uuid)
  TO app_api;

REVOKE ALL ON FUNCTION app.summarize_caller_usage(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.summarize_caller_usage(uuid, text, bigint)
  TO app_api;

REVOKE ALL ON FUNCTION app.summarize_company_usage(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.summarize_company_usage(uuid, text, bigint)
  TO app_api;
