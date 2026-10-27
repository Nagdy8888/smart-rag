-- Preserve stored history while preventing restored prose from bypassing
-- current source permissions, deletion, or current-version visibility.
CREATE FUNCTION app.run_knowledge_history_unavailable(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint, p_run_id uuid
) RETURNS boolean LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  IF NOT EXISTS(SELECT 1 FROM app.runs r JOIN app.conversations c ON c.id=r.conversation_id
    WHERE r.id=p_run_id AND r.creator_user_id=caller_user_id AND c.deleted_at IS NULL) THEN RETURN true; END IF;
  RETURN EXISTS(SELECT 1 FROM app.citations c LEFT JOIN app.document_chunks ch ON ch.id=c.chunk_id
    LEFT JOIN app.documents d ON d.id=ch.document_id
    WHERE c.run_id=p_run_id AND (
      ch.id IS NULL OR ch.deleted_at IS NOT NULL OR d.deleted_at IS NOT NULL
      OR ch.version_id IS DISTINCT FROM d.current_version_id
      OR NOT app.caller_can_read_document(caller_user_id,caller_role,ch.document_id)
    ));
END; $fn$;

CREATE FUNCTION app.purge_deleted_conversation_knowledge() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
BEGIN
  DELETE FROM app.conversation_knowledge_context WHERE conversation_id=NEW.id;
  DELETE FROM app.knowledge_maintenance_reviews k
    WHERE k.source_run_id IN (SELECT id FROM app.runs WHERE conversation_id=NEW.id)
       OR k.source_feedback_id IN (
         SELECT f.id FROM app.user_feedback f JOIN app.runs r ON r.id=f.run_id
         WHERE r.conversation_id=NEW.id);
  RETURN NEW;
END; $fn$;
CREATE TRIGGER conversations_purge_knowledge AFTER UPDATE OF deleted_at ON app.conversations
  FOR EACH ROW WHEN (OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL)
  EXECUTE FUNCTION app.purge_deleted_conversation_knowledge();
REVOKE ALL ON FUNCTION app.purge_deleted_conversation_knowledge()
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app.run_knowledge_history_unavailable(uuid,text,bigint,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.run_knowledge_history_unavailable(uuid,text,bigint,uuid) TO app_api;

ALTER FUNCTION app.list_run_events_after(uuid,text,bigint,uuid,bigint)
  RENAME TO list_run_events_before_knowledge_guard;
REVOKE ALL ON FUNCTION app.list_run_events_before_knowledge_guard(uuid,text,bigint,uuid,bigint)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
CREATE FUNCTION app.list_run_events_after(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_run_id uuid, p_after_sequence bigint
) RETURNS TABLE(run_id uuid, sequence bigint, event_type text, payload jsonb, created_at timestamptz)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
BEGIN
  IF app.run_knowledge_history_unavailable(caller_user_id,caller_role,caller_authorization_version,p_run_id) THEN
    RAISE EXCEPTION 'query_admission:not_found'; END IF;
  RETURN QUERY SELECT * FROM app.list_run_events_before_knowledge_guard(
    caller_user_id,caller_role,caller_authorization_version,p_run_id,p_after_sequence);
END; $fn$;
REVOKE ALL ON FUNCTION app.list_run_events_after(uuid,text,bigint,uuid,bigint) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.list_run_events_after(uuid,text,bigint,uuid,bigint) TO app_api;

CREATE OR REPLACE FUNCTION app.get_run_knowledge_result(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint, p_run_id uuid
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
DECLARE result jsonb;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  SELECT COALESCE(r.knowledge_result, '{}'::jsonb) INTO result
    FROM app.runs r JOIN app.conversations c ON c.id=r.conversation_id
    WHERE r.id=p_run_id AND r.creator_user_id=caller_user_id AND c.deleted_at IS NULL;
  IF NOT FOUND THEN RETURN NULL; END IF;
  IF app.run_knowledge_history_unavailable(caller_user_id,caller_role,caller_authorization_version,p_run_id) THEN RETURN '{}'::jsonb; END IF;
  RETURN result;
END; $fn$;
