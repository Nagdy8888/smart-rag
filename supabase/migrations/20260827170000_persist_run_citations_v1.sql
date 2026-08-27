-- Ask Sources: creator-only citation persistence for verified query runs.

CREATE OR REPLACE FUNCTION app.insert_run_citation(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_citation_index integer,
  p_chunk_id uuid,
  p_snippet text,
  p_provenance jsonb
)
RETURNS TABLE (citation_id uuid)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  run_row app.runs%ROWTYPE;
  inserted_id uuid;
  bounded_snippet text;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'query_citation:authorization_rejected';
  END IF;

  IF p_citation_index IS NULL OR p_citation_index < 0 THEN
    RAISE EXCEPTION 'query_citation:invalid_index';
  END IF;

  IF p_provenance IS NULL THEN
    RAISE EXCEPTION 'query_citation:invalid_provenance';
  END IF;

  bounded_snippet := left(coalesce(p_snippet, ''), 500);

  SELECT * INTO run_row
  FROM app.runs AS r
  WHERE r.id = p_run_id;

  IF NOT FOUND OR run_row.creator_user_id IS DISTINCT FROM caller_user_id THEN
    RAISE EXCEPTION 'query_citation:run_forbidden';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.conversations AS c
    WHERE c.id = run_row.conversation_id
      AND c.deleted_at IS NULL
      AND c.creator_user_id = caller_user_id
  ) THEN
    RAISE EXCEPTION 'query_citation:conversation_forbidden';
  END IF;

  INSERT INTO app.citations (
    run_id,
    chunk_id,
    citation_index,
    snippet,
    provenance
  )
  VALUES (
    p_run_id,
    p_chunk_id,
    p_citation_index,
    bounded_snippet,
    p_provenance
  )
  RETURNING app.citations.id INTO inserted_id;

  citation_id := inserted_id;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.insert_run_citation(
  uuid, text, bigint, uuid, integer, uuid, text, jsonb
) IS
  'Creator-only insert of one verified citation row for an owned query run.';

REVOKE ALL ON FUNCTION app.insert_run_citation(
  uuid, text, bigint, uuid, integer, uuid, text, jsonb
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.insert_run_citation(
  uuid, text, bigint, uuid, integer, uuid, text, jsonb
) TO app_api;
