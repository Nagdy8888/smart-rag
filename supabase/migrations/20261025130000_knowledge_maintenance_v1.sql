-- Reports are private unless their creator explicitly shares them for review.
ALTER TABLE app.user_feedback ADD COLUMN share_with_reviewers boolean NOT NULL DEFAULT false;
CREATE TABLE app.knowledge_maintenance_reviews (
  kind text NOT NULL CHECK (kind IN ('missing_owner','overdue_review','feedback','insufficient_evidence','conflicting_evidence')),
  source_id uuid NOT NULL,
  source_feedback_id uuid REFERENCES app.user_feedback(id) ON DELETE CASCADE,
  source_run_id uuid REFERENCES app.runs(id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')),
  assigned_to uuid REFERENCES app.profiles(user_id) ON DELETE SET NULL,
  reason text CHECK (char_length(reason) <= 2000),
  revision bigint NOT NULL DEFAULT 1,
  updated_by uuid NOT NULL REFERENCES app.profiles(user_id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(kind, source_id)
);
ALTER TABLE app.knowledge_maintenance_reviews ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.knowledge_maintenance_reviews FORCE ROW LEVEL SECURITY;
REVOKE ALL ON app.knowledge_maintenance_reviews FROM PUBLIC, anon, authenticated, app_api, app_worker;

CREATE FUNCTION app.share_knowledge_feedback(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint, p_feedback_id uuid
) RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, app AS $fn$
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  UPDATE app.user_feedback f SET share_with_reviewers = true
  FROM app.runs r JOIN app.conversations c ON c.id = r.conversation_id
  WHERE f.id = p_feedback_id AND f.user_id = caller_user_id AND r.id = f.run_id
    AND r.creator_user_id = caller_user_id AND c.deleted_at IS NULL;
  IF NOT FOUND THEN RAISE EXCEPTION 'documents:not_found'; END IF;
  PERFORM app.append_audit_event('knowledge.feedback_shared', caller_user_id,
    caller_role::app.user_role, 'feedback', p_feedback_id, app.current_authorization_version(), '{}'::jsonb);
END; $fn$;

CREATE FUNCTION app.knowledge_run_review_allowed(p_user uuid, p_role text, p_run uuid)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
  SELECT p_role IN ('owner','admin') AND EXISTS (
    SELECT 1 FROM app.runs r JOIN app.conversations c ON c.id = r.conversation_id
    WHERE r.id = p_run AND c.deleted_at IS NULL AND (
      r.creator_user_id = p_user OR EXISTS (
        SELECT 1 FROM app.user_feedback f WHERE f.run_id = r.id AND f.share_with_reviewers
      )
    )
  ) AND NOT EXISTS (
    SELECT 1 FROM app.citations c LEFT JOIN app.document_chunks ch ON ch.id = c.chunk_id
    LEFT JOIN app.documents d ON d.id = ch.document_id
    WHERE c.run_id = p_run AND (
      ch.id IS NULL OR ch.deleted_at IS NOT NULL OR d.deleted_at IS NOT NULL
      OR ch.version_id IS DISTINCT FROM d.current_version_id
      OR NOT app.caller_can_read_document(p_user, p_role, ch.document_id)
    )
  );
$fn$;

CREATE FUNCTION app.list_knowledge_maintenance(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_limit integer DEFAULT 50, p_offset integer DEFAULT 0
) RETURNS TABLE(kind text, source_id uuid, document_id uuid, run_id uuid,
  title text, report jsonb, status text, assigned_to uuid, reason text, revision bigint)
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = pg_catalog, app AS $fn$
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  IF caller_role NOT IN ('owner','admin') THEN RAISE EXCEPTION 'documents:forbidden'; END IF;
  RETURN QUERY WITH candidates AS (
    SELECT 'missing_owner'::text AS kind, d.id AS source_id, d.id AS document_id,
      NULL::uuid AS run_id, d.title, '{}'::jsonb AS report
    FROM app.documents d WHERE d.deleted_at IS NULL AND d.knowledge_owner_user_id IS NULL
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
    UNION ALL
    SELECT 'overdue_review', d.id, d.id, NULL::uuid, d.title, '{}'::jsonb
    FROM app.documents d WHERE d.deleted_at IS NULL AND d.review_due_at < current_date
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
    UNION ALL
    SELECT 'feedback', f.id, NULL::uuid, f.run_id, f.tag,
      jsonb_build_object('comment', f.comment,
        'question', (SELECT left(m.content, 4000) FROM app.messages m WHERE m.run_id = f.run_id AND m.role = 'user' LIMIT 1),
        'answer', (SELECT left(m.content, 16384) FROM app.messages m WHERE m.run_id = f.run_id AND m.role = 'assistant' LIMIT 1))
    FROM app.user_feedback f WHERE f.rating = 1
      AND (f.user_id = caller_user_id OR f.share_with_reviewers)
      AND app.knowledge_run_review_allowed(caller_user_id, caller_role, f.run_id)
    UNION ALL
    SELECT r.knowledge_result->>'outcome', r.id, NULL::uuid, r.id,
      r.knowledge_result->>'outcome', '{}'::jsonb
    FROM app.runs r WHERE r.knowledge_result->>'outcome' IN ('insufficient_evidence','conflicting_evidence')
      AND app.knowledge_run_review_allowed(caller_user_id, caller_role, r.id)
  ) SELECT c.kind, c.source_id, c.document_id, c.run_id, c.title, c.report,
    COALESCE(s.status, 'open'), s.assigned_to, s.reason, COALESCE(s.revision, 0)
    FROM candidates c LEFT JOIN app.knowledge_maintenance_reviews s USING(kind, source_id)
    ORDER BY c.kind, c.source_id LIMIT greatest(1, least(p_limit, 100)) OFFSET greatest(0, least(p_offset, 10000));
END; $fn$;

CREATE FUNCTION app.update_knowledge_maintenance(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_kind text, p_source_id uuid, p_body jsonb
) RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, app AS $fn$
DECLARE existing_revision bigint; item_visible boolean := false;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected'; END IF;
  IF caller_role NOT IN ('owner','admin') THEN RAISE EXCEPTION 'documents:forbidden'; END IF;
  IF p_kind IN ('missing_owner','overdue_review') THEN
    SELECT EXISTS(SELECT 1 FROM app.documents d WHERE d.id = p_source_id AND d.deleted_at IS NULL
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
      AND ((p_kind = 'missing_owner' AND d.knowledge_owner_user_id IS NULL)
        OR (p_kind = 'overdue_review' AND d.review_due_at < current_date))) INTO item_visible;
  ELSIF p_kind = 'feedback' THEN
    SELECT EXISTS(SELECT 1 FROM app.user_feedback f WHERE f.id = p_source_id AND f.rating = 1
      AND (f.user_id = caller_user_id OR f.share_with_reviewers)
      AND app.knowledge_run_review_allowed(caller_user_id, caller_role, f.run_id)) INTO item_visible;
  ELSIF p_kind IN ('insufficient_evidence','conflicting_evidence') THEN
    SELECT EXISTS(SELECT 1 FROM app.runs r WHERE r.id = p_source_id AND r.knowledge_result->>'outcome' = p_kind
      AND app.knowledge_run_review_allowed(caller_user_id, caller_role, r.id)) INTO item_visible;
  END IF;
  IF NOT item_visible THEN RAISE EXCEPTION 'documents:not_found'; END IF;
  IF p_body->>'status' IS NULL OR p_body->>'status' NOT IN ('open','resolved','dismissed')
    OR char_length(COALESCE(p_body->>'reason','')) > 2000
    OR (p_body->>'status' IN ('resolved','dismissed') AND btrim(COALESCE(p_body->>'reason','')) = '')
  THEN RAISE EXCEPTION 'documents:invalid_review'; END IF;
  IF p_body->>'assigned_to' IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.profiles WHERE user_id = (p_body->>'assigned_to')::uuid
    AND role IN ('owner','admin') AND disabled_at IS NULL
  ) THEN RAISE EXCEPTION 'documents:invalid_review'; END IF;
  -- Serialize first-insert and updates, including the absent-row case.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_kind || ':' || p_source_id::text, 0));
  SELECT revision INTO existing_revision FROM app.knowledge_maintenance_reviews
    WHERE kind = p_kind AND source_id = p_source_id FOR UPDATE;
  IF COALESCE(existing_revision, 0) IS DISTINCT FROM (p_body->>'expected_revision')::bigint THEN
    RAISE EXCEPTION 'documents:governance_conflict'; END IF;
  INSERT INTO app.knowledge_maintenance_reviews(kind, source_id, status, assigned_to, reason, updated_by, source_feedback_id, source_run_id)
  VALUES(p_kind, p_source_id, p_body->>'status', (p_body->>'assigned_to')::uuid,
    p_body->>'reason', caller_user_id,
    CASE WHEN p_kind='feedback' THEN p_source_id ELSE NULL END,
    CASE WHEN p_kind IN ('insufficient_evidence','conflicting_evidence') THEN p_source_id ELSE NULL END)
  ON CONFLICT(kind, source_id) DO UPDATE SET status = EXCLUDED.status,
    assigned_to = EXCLUDED.assigned_to, reason = EXCLUDED.reason, updated_by = EXCLUDED.updated_by,
    revision = app.knowledge_maintenance_reviews.revision + 1, updated_at = now();
  PERFORM app.append_audit_event('knowledge.maintenance_updated', caller_user_id,
    caller_role::app.user_role, 'knowledge_review', p_source_id, app.current_authorization_version(),
    jsonb_build_object('kind', p_kind, 'status', p_body->>'status'));
END; $fn$;

REVOKE ALL ON FUNCTION app.share_knowledge_feedback(uuid,text,bigint,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.knowledge_run_review_allowed(uuid,text,uuid) FROM PUBLIC, anon, authenticated, app_api;
REVOKE ALL ON FUNCTION app.list_knowledge_maintenance(uuid,text,bigint,integer,integer) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.update_knowledge_maintenance(uuid,text,bigint,text,uuid,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.share_knowledge_feedback(uuid,text,bigint,uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.list_knowledge_maintenance(uuid,text,bigint,integer,integer) TO app_api;
GRANT EXECUTE ON FUNCTION app.update_knowledge_maintenance(uuid,text,bigint,text,uuid,jsonb) TO app_api;
