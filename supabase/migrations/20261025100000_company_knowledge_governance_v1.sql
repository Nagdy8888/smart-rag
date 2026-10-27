-- Company knowledge authority is distinct from content-processing approval/ACL.
ALTER TABLE app.company_settings
  ADD COLUMN knowledge_reliability_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE app.documents
  ADD COLUMN knowledge_generation bigint NOT NULL DEFAULT 1 CHECK (knowledge_generation > 0),
  ADD COLUMN knowledge_owner_user_id uuid REFERENCES app.profiles(user_id) ON DELETE SET NULL,
  ADD COLUMN knowledge_area text CHECK (char_length(knowledge_area) BETWEEN 1 AND 120),
  ADD COLUMN review_due_at date;
ALTER TABLE app.document_versions
  ADD COLUMN authority_status text NOT NULL DEFAULT 'unreviewed'
    CHECK (authority_status IN ('unreviewed', 'draft', 'approved', 'superseded')),
  ADD COLUMN superseded_by_version_id uuid REFERENCES app.document_versions(id),
  ADD COLUMN governance_generation bigint NOT NULL DEFAULT 1 CHECK (governance_generation > 0),
  ADD CONSTRAINT knowledge_no_self_supersession CHECK (superseded_by_version_id IS DISTINCT FROM id),
  ADD CONSTRAINT knowledge_replacement_status CHECK (
    (authority_status = 'superseded') = (superseded_by_version_id IS NOT NULL)
  );

CREATE FUNCTION app.get_document_governance(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_document_id uuid, p_version_id uuid
) RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path = pg_catalog, app AS $fn$
DECLARE result jsonb;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;
  IF NOT app.caller_can_read_document(caller_user_id, caller_role, p_document_id) THEN
    RETURN NULL;
  END IF;
  SELECT jsonb_build_object(
    'version_id', v.id, 'version_number', v.version_number,
    'owner_user_id', d.knowledge_owner_user_id, 'owner_display_name', p.display_name,
    'knowledge_area', d.knowledge_area, 'review_due_at', d.review_due_at,
    'authority_status', COALESCE(v.authority_status, 'unreviewed'),
    'effective_at', v.effective_at, 'superseded_by_version_id', v.superseded_by_version_id,
    'governance_generation', d.knowledge_generation,
    'reliability_enabled', s.knowledge_reliability_enabled
  ) INTO result
  FROM app.documents d CROSS JOIN app.company_settings s
  LEFT JOIN app.document_versions v ON v.id = COALESCE(p_version_id, d.current_version_id)
    AND v.document_id = d.id AND v.deleted_at IS NULL
  LEFT JOIN app.profiles p ON p.user_id=d.knowledge_owner_user_id
  WHERE d.id = p_document_id AND d.deleted_at IS NULL
    AND (p_version_id IS NULL OR v.id IS NOT NULL);
  RETURN result;
END; $fn$;

CREATE FUNCTION app.get_document_governance(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint, p_document_id uuid
) RETURNS jsonb LANGUAGE sql STABLE SECURITY INVOKER SET search_path = pg_catalog, app AS $fn$
  SELECT app.get_document_governance(caller_user_id,caller_role,caller_authorization_version,p_document_id,NULL);
$fn$;

CREATE FUNCTION app.update_document_governance(
  caller_user_id uuid, caller_role text, caller_authorization_version bigint,
  p_document_id uuid, p_body jsonb
) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = pg_catalog, app AS $fn$
DECLARE
  doc app.documents%ROWTYPE;
  ver app.document_versions%ROWTYPE;
  next_status text := p_body->>'authority_status';
  replacement uuid := (p_body->>'superseded_by_version_id')::uuid;
  owner_id uuid := (p_body->>'owner_user_id')::uuid;
BEGIN
  IF NOT app.validate_caller_context(caller_user_id, caller_role, caller_authorization_version) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;
  IF caller_role NOT IN ('owner', 'admin') THEN RAISE EXCEPTION 'documents:forbidden'; END IF;
  SELECT * INTO doc FROM app.documents WHERE id = p_document_id AND deleted_at IS NULL FOR UPDATE;
  IF NOT FOUND OR NOT app.caller_can_read_document(caller_user_id, caller_role, p_document_id) THEN RETURN NULL; END IF;
  SELECT * INTO ver FROM app.document_versions WHERE id = (p_body->>'version_id')::uuid AND document_id = doc.id AND deleted_at IS NULL FOR UPDATE;
  IF NOT FOUND OR ver.id IS DISTINCT FROM (p_body->>'version_id')::uuid
     OR doc.knowledge_generation IS DISTINCT FROM (p_body->>'expected_generation')::bigint THEN
    RAISE EXCEPTION 'documents:governance_conflict';
  END IF;
  IF next_status IS NULL OR next_status NOT IN ('unreviewed','draft','approved','superseded')
     OR (next_status = 'approved' AND (owner_id IS NULL OR p_body->>'effective_at' IS NULL))
     OR ((next_status = 'superseded') IS DISTINCT FROM (replacement IS NOT NULL))
     OR replacement = ver.id THEN RAISE EXCEPTION 'documents:invalid_governance'; END IF;
  IF owner_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.profiles WHERE user_id = owner_id AND disabled_at IS NULL
  ) THEN RAISE EXCEPTION 'documents:invalid_governance'; END IF;
  IF replacement IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM app.document_versions r
    JOIN app.documents d ON d.id = r.document_id
    WHERE r.id = replacement AND r.document_id = doc.id AND r.deleted_at IS NULL
      AND r.authority_status = 'approved' AND d.deleted_at IS NULL
      AND d.current_version_id = r.id
      AND r.superseded_by_version_id IS NULL
  ) THEN RAISE EXCEPTION 'documents:invalid_governance'; END IF;
  UPDATE app.documents SET knowledge_owner_user_id = owner_id,
    knowledge_area = p_body->>'knowledge_area', review_due_at = (p_body->>'review_due_at')::date,
    knowledge_generation = knowledge_generation + 1, updated_at = now() WHERE id = doc.id;
  UPDATE app.document_versions SET authority_status = next_status,
    effective_at = (p_body->>'effective_at')::timestamptz,
    superseded_by_version_id = replacement, governance_generation = governance_generation + 1,
    updated_at = now() WHERE id = ver.id;
  -- Existing ID-only caches include company visibility generation. No re-embedding.
  UPDATE app.company_settings SET visibility_generation = visibility_generation + 1;
  PERFORM app.append_audit_event('document.governance_updated', caller_user_id,
    caller_role::app.user_role, 'document', doc.id, app.current_authorization_version(),
    jsonb_build_object('version_id', ver.id, 'authority_status', next_status,
      'governance_generation', doc.knowledge_generation + 1));
  RETURN app.get_document_governance(caller_user_id, caller_role, caller_authorization_version, doc.id, ver.id);
END; $fn$;

REVOKE ALL ON FUNCTION app.get_document_governance(uuid,text,bigint,uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.update_document_governance(uuid,text,bigint,uuid,jsonb) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_document_governance(uuid,text,bigint,uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.update_document_governance(uuid,text,bigint,uuid,jsonb) TO app_api;

REVOKE ALL ON FUNCTION app.get_document_governance(uuid,text,bigint,uuid,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_document_governance(uuid,text,bigint,uuid,uuid) TO app_api;
