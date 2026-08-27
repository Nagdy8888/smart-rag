-- Run Details: derive billed USD from stored token counts using list-price pins.

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
      sum(
        CASE
          WHEN u.usage_kind = 'embedding' THEN
            (u.prompt_tokens::numeric * 0.13) / 1000000.0
          ELSE
            (u.prompt_tokens::numeric * 0.15) / 1000000.0
            + (u.completion_tokens::numeric * 0.60) / 1000000.0
        END
      ),
      0
    ),
    COALESCE(sum(u.prompt_tokens), 0)::bigint,
    COALESCE(sum(u.completion_tokens), 0)::bigint,
    count(u.id)::bigint
  FROM app.llm_usage AS u
  WHERE u.run_id = p_run_id;
END;
$fn$;

COMMENT ON FUNCTION app.summarize_run_usage(uuid, text, bigint, uuid) IS
  'Creator-only billed usage totals for one owned query run. USD is recomputed from token counts using pinned OpenAI list prices (gpt-4o-mini chat, text-embedding-3-large embeddings).';

REVOKE ALL ON FUNCTION app.summarize_run_usage(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.summarize_run_usage(uuid, text, bigint, uuid)
  TO app_api;
