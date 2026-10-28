-- Recorded presentation metadata only. Never infer or backfill answer origin.
CREATE FUNCTION app.get_run_presentation_v1(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_run_id uuid
)
RETURNS TABLE (requested_search_scope text, answer_origin text)
LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF p_run_id IS NULL THEN RETURN; END IF;
  RETURN QUERY
  SELECT r.requested_search_scope,
    (SELECT e.payload->>'origin' FROM app.run_events e
     WHERE e.run_id = r.id AND e.event_type = 'answer_origin'
     ORDER BY e.sequence DESC LIMIT 1)
  FROM app.get_query_run_v3(
    caller_user_id, caller_role, caller_authorization_version, p_run_id
  ) r;
END;
$fn$;
REVOKE ALL ON FUNCTION app.get_run_presentation_v1(uuid,text,bigint,uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_run_presentation_v1(uuid,text,bigint,uuid) TO app_api;
COMMENT ON FUNCTION app.get_run_presentation_v1(uuid,text,bigint,uuid) IS
  'Creator-authorized recorded requested scope and event origin; missing history stays null.';
