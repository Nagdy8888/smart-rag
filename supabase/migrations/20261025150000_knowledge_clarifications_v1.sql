-- Pending clarification belongs to the conversation creator, never global memory.
ALTER TABLE app.conversation_knowledge_context
  ADD COLUMN clarification_original text CHECK (char_length(clarification_original) <= 2000),
  ADD COLUMN clarification_question text CHECK (char_length(clarification_question) <= 300),
  ADD COLUMN clarification_run_id uuid REFERENCES app.runs(id) ON DELETE SET NULL;
ALTER TABLE app.runs ADD COLUMN knowledge_resolved_query text CHECK (char_length(knowledge_resolved_query) <= 2000);

CREATE FUNCTION app.prepare_knowledge_clarification(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_run_id uuid, p_query text, p_question text DEFAULT NULL
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
DECLARE run app.runs%ROWTYPE; pending app.conversation_knowledge_context%ROWTYPE; resolved text;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  SELECT r.* INTO run FROM app.runs r JOIN app.conversations c ON c.id=r.conversation_id
    WHERE r.id=p_run_id AND r.creator_user_id=caller_user_id AND c.deleted_at IS NULL FOR UPDATE OF r;
  IF NOT FOUND THEN RAISE EXCEPTION 'documents:not_found'; END IF;
  IF NOT (SELECT knowledge_reliability_enabled FROM app.company_settings) THEN
    RETURN jsonb_build_object('query',p_query,'resumed',false); END IF;
  IF char_length(p_query)>2000 OR btrim(p_query)='' THEN RAISE EXCEPTION 'documents:invalid_query'; END IF;
  PERFORM 1 FROM app.conversations WHERE id=run.conversation_id FOR UPDATE;
  SELECT * INTO pending FROM app.conversation_knowledge_context WHERE conversation_id=run.conversation_id FOR UPDATE;
  IF p_question IS NOT NULL THEN
    IF char_length(p_question)>300 OR btrim(p_question)='' OR run.knowledge_resolved_query IS NOT NULL THEN
      RAISE EXCEPTION 'documents:invalid_clarification'; END IF;
    INSERT INTO app.conversation_knowledge_context(conversation_id,clarification_original,clarification_question,clarification_run_id)
      VALUES(run.conversation_id,p_query,p_question,p_run_id)
      ON CONFLICT(conversation_id) DO UPDATE SET clarification_original=EXCLUDED.clarification_original,
        clarification_question=EXCLUDED.clarification_question,clarification_run_id=EXCLUDED.clarification_run_id;
    RETURN jsonb_build_object('query',p_query,'resumed',false);
  END IF;
  IF run.knowledge_resolved_query IS NOT NULL THEN
    RETURN jsonb_build_object('query',run.knowledge_resolved_query,'resumed',true); END IF;
  IF pending.clarification_original IS NOT NULL AND pending.clarification_run_id IS DISTINCT FROM p_run_id THEN
    resolved := pending.clarification_original || E'\nUser clarification: ' || p_query;
    IF char_length(resolved)>2000 THEN RAISE EXCEPTION 'documents:clarification_context_too_long'; END IF;
    UPDATE app.runs SET knowledge_resolved_query=resolved WHERE id=p_run_id;
    UPDATE app.conversation_knowledge_context SET clarification_original=NULL,
      clarification_question=NULL,clarification_run_id=NULL WHERE conversation_id=run.conversation_id;
    RETURN jsonb_build_object('query',resolved,'resumed',true);
  END IF;
  RETURN jsonb_build_object('query',p_query,'resumed',false);
END; $fn$;
REVOKE ALL ON FUNCTION app.prepare_knowledge_clarification(uuid,text,bigint,uuid,text,text) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.prepare_knowledge_clarification(uuid,text,bigint,uuid,text,text) TO app_api;
