-- One explicitly selected document per conversation in v1. Empty means all
-- authorized company documents. Scope never grants access or changes ACLs.
CREATE TABLE app.conversation_knowledge_context (
  conversation_id uuid PRIMARY KEY REFERENCES app.conversations(id) ON DELETE CASCADE,
  document_id uuid REFERENCES app.documents(id),
  revision bigint NOT NULL DEFAULT 1
);
ALTER TABLE app.conversation_knowledge_context ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.conversation_knowledge_context FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app.conversation_knowledge_context FROM PUBLIC, anon, authenticated, app_api, app_worker;
ALTER TABLE app.runs ADD COLUMN knowledge_document_id uuid REFERENCES app.documents(id),
  ADD COLUMN knowledge_version_id uuid REFERENCES app.document_versions(id);

CREATE FUNCTION app.conversation_knowledge_scope(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_conversation_id uuid, p_update boolean DEFAULT false, p_document_id uuid DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
DECLARE doc_id uuid; doc_title text; enabled boolean;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  PERFORM 1 FROM app.conversations WHERE id=p_conversation_id AND creator_user_id=caller_user_id AND deleted_at IS NULL FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'documents:not_found'; END IF;
  SELECT knowledge_reliability_enabled INTO enabled FROM app.company_settings;
  IF p_update THEN
    IF p_document_id IS NOT NULL AND NOT EXISTS(SELECT 1 FROM app.documents d
      WHERE d.id=p_document_id AND d.deleted_at IS NULL AND d.current_version_id IS NOT NULL
        AND app.caller_can_read_document(caller_user_id,caller_role,d.id)) THEN
      RAISE EXCEPTION 'documents:not_found'; END IF;
    INSERT INTO app.conversation_knowledge_context(conversation_id,document_id)
      VALUES(p_conversation_id,p_document_id)
      ON CONFLICT(conversation_id) DO UPDATE SET document_id=EXCLUDED.document_id,
        revision=app.conversation_knowledge_context.revision+1;
  END IF;
  SELECT document_id INTO doc_id FROM app.conversation_knowledge_context WHERE conversation_id=p_conversation_id;
  IF doc_id IS NOT NULL THEN
    SELECT title INTO doc_title FROM app.documents d WHERE d.id=doc_id AND d.deleted_at IS NULL
      AND app.caller_can_read_document(caller_user_id,caller_role,d.id);
    -- Never return a revoked title, and never silently broaden a saved scope.
    IF NOT FOUND THEN RETURN jsonb_build_object('document_id',NULL,'title',NULL,'unavailable',true,'enabled',enabled); END IF;
  END IF;
  RETURN jsonb_build_object('document_id',doc_id,'title',doc_title,'unavailable',false,'enabled',enabled);
END; $fn$;

CREATE FUNCTION app.snapshot_knowledge_run_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
DECLARE selected uuid; user_role text;
BEGIN
  IF NOT (SELECT knowledge_reliability_enabled FROM app.company_settings) THEN RETURN NEW; END IF;
  SELECT k.document_id INTO selected FROM app.conversation_knowledge_context k WHERE k.conversation_id=NEW.conversation_id;
  IF selected IS NULL THEN RETURN NEW; END IF;
  SELECT role::text INTO user_role FROM app.profiles WHERE user_id=NEW.creator_user_id AND disabled_at IS NULL;
  SELECT d.id,d.current_version_id INTO NEW.knowledge_document_id,NEW.knowledge_version_id
    FROM app.documents d WHERE d.id=selected AND d.deleted_at IS NULL AND d.current_version_id IS NOT NULL
    AND app.caller_can_read_document(NEW.creator_user_id,user_role,d.id);
  IF NOT FOUND THEN RAISE EXCEPTION 'query_admission:not_found'; END IF;
  RETURN NEW;
END; $fn$;
CREATE TRIGGER runs_snapshot_knowledge_scope BEFORE INSERT ON app.runs FOR EACH ROW EXECUTE FUNCTION app.snapshot_knowledge_run_scope();

CREATE FUNCTION app.get_run_knowledge_scope(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint, p_run_id uuid
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
DECLARE doc uuid; ver uuid;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  SELECT r.knowledge_document_id,r.knowledge_version_id INTO doc,ver FROM app.runs r
    JOIN app.conversations c ON c.id=r.conversation_id
    WHERE r.id=p_run_id AND r.creator_user_id=caller_user_id AND c.deleted_at IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'documents:not_found'; END IF;
  IF doc IS NULL THEN RETURN NULL; END IF;
  IF NOT EXISTS(SELECT 1 FROM app.documents d WHERE d.id=doc AND d.current_version_id=ver
    AND d.deleted_at IS NULL AND app.caller_can_read_document(caller_user_id,caller_role,d.id)) THEN
    RAISE EXCEPTION 'documents:not_found'; END IF;
  RETURN jsonb_build_object('document_id',doc,'version_id',ver);
END; $fn$;
REVOKE ALL ON FUNCTION app.conversation_knowledge_scope(uuid,text,bigint,uuid,boolean,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.snapshot_knowledge_run_scope() FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app.get_run_knowledge_scope(uuid,text,bigint,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.conversation_knowledge_scope(uuid,text,bigint,uuid,boolean,uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.get_run_knowledge_scope(uuid,text,bigint,uuid) TO app_api;
