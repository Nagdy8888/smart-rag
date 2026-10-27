-- Final knowledge outcomes are recorded before publication and survive event GC.
ALTER TABLE app.runs ADD COLUMN knowledge_result jsonb;

CREATE FUNCTION app.record_run_knowledge_result(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_run_id uuid, p_result jsonb
) RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, app AS $fn$
DECLARE existing jsonb;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;
  SELECT r.knowledge_result INTO existing FROM app.runs r
  JOIN app.conversations c ON c.id = r.conversation_id
  WHERE r.id = p_run_id AND r.creator_user_id = caller_user_id AND c.deleted_at IS NULL
  FOR UPDATE OF r;
  IF NOT FOUND THEN RAISE EXCEPTION 'documents:not_found'; END IF;
  IF p_result->>'outcome' IS NULL OR p_result->>'outcome' NOT IN
    ('supported','partial','insufficient_evidence','conflicting_evidence')
    OR jsonb_typeof(p_result->'limitations') IS DISTINCT FROM 'array'
    OR octet_length(p_result::text) > 4096
  THEN RAISE EXCEPTION 'documents:invalid_knowledge_result'; END IF;
  IF existing IS NOT NULL AND existing <> p_result THEN
    RAISE EXCEPTION 'documents:knowledge_result_conflict';
  END IF;
  UPDATE app.runs SET knowledge_result = p_result WHERE id = p_run_id;
END; $fn$;

CREATE FUNCTION app.get_run_knowledge_result(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint, p_run_id uuid
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, app AS $fn$
DECLARE result jsonb;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;
  SELECT COALESCE(r.knowledge_result, '{}'::jsonb) INTO result
  FROM app.runs r JOIN app.conversations c ON c.id = r.conversation_id
  WHERE r.id = p_run_id AND r.creator_user_id = caller_user_id AND c.deleted_at IS NULL;
  RETURN result;
END; $fn$;
REVOKE ALL ON FUNCTION app.record_run_knowledge_result(uuid,text,bigint,uuid,jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.get_run_knowledge_result(uuid,text,bigint,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.record_run_knowledge_result(uuid,text,bigint,uuid,jsonb) TO app_api;
GRANT EXECUTE ON FUNCTION app.get_run_knowledge_result(uuid,text,bigint,uuid) TO app_api;
