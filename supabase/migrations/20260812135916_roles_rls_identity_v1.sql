-- Phase 2 Packet 3: least-privilege roles, RLS, ACL, identity propagation RPCs.

-- ---------------------------------------------------------------------------
-- Runtime roles (NOLOGIN for local GRANT testing; passwords live outside git)
-- ---------------------------------------------------------------------------

DO $$
BEGIN
  CREATE ROLE app_api NOLOGIN;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  CREATE ROLE app_worker NOLOGIN;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  CREATE ROLE app_checkpointer NOLOGIN;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  CREATE ROLE app_lightrag NOLOGIN;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  CREATE ROLE app_audit_writer NOLOGIN;
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

COMMENT ON ROLE app_api IS
  'FastAPI transaction-pooled RPC role. EXECUTE on approved app/private functions only.';
COMMENT ON ROLE app_worker IS
  'Worker ingestion/job role. Canonical writes and queue tables; no private conversations.';
COMMENT ON ROLE app_checkpointer IS
  'LangGraph checkpointer role. langgraph schema only; session/direct pool.';
COMMENT ON ROLE app_lightrag IS
  'LightRAG storage role. lightrag schema only; session/direct pool.';
COMMENT ON ROLE app_audit_writer IS
  'Append-only audit insert path. No UPDATE/DELETE.';

-- ---------------------------------------------------------------------------
-- Caller-context validation and document ACL helpers
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.current_authorization_version()
RETURNS bigint
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT cs.authorization_version
  FROM app.company_settings AS cs
  WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid;
$$;

COMMENT ON FUNCTION app.current_authorization_version() IS
  'Returns the singleton company authorization_version for RPC snapshot checks.';

CREATE OR REPLACE FUNCTION app.validate_caller_context(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  live_version bigint;
  profile_role app.user_role;
  disabled_at timestamptz;
BEGIN
  IF caller_user_id IS NULL OR caller_role IS NULL OR caller_authorization_version IS NULL THEN
    RETURN false;
  END IF;

  IF caller_role NOT IN ('owner', 'admin', 'member', 'viewer') THEN
    RETURN false;
  END IF;

  SELECT cs.authorization_version
  INTO live_version
  FROM app.company_settings AS cs
  WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid;

  IF caller_authorization_version IS DISTINCT FROM live_version THEN
    RETURN false;
  END IF;

  SELECT p.role, p.disabled_at
  INTO profile_role, disabled_at
  FROM app.profiles AS p
  WHERE p.user_id = caller_user_id;

  IF NOT FOUND OR disabled_at IS NOT NULL THEN
    RETURN false;
  END IF;

  IF profile_role::text IS DISTINCT FROM caller_role THEN
    RETURN false;
  END IF;

  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION app.validate_caller_context(uuid, text, bigint) IS
  'Fail-closed membership + authorization_version check for server-derived RPC context.';

CREATE OR REPLACE FUNCTION app.caller_can_read_document(
  caller_user_id uuid,
  caller_role text,
  p_document_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM app.documents AS d
    WHERE d.id = p_document_id
      AND d.deleted_at IS NULL
      AND (
        d.visibility = 'company_visible'::app.document_visibility
        OR caller_role IN ('owner', 'admin')
        OR EXISTS (
          SELECT 1
          FROM app.document_acl AS acl
          WHERE acl.document_id = d.id
            AND acl.grantee_user_id = caller_user_id
            AND acl.revoked_at IS NULL
        )
      )
  );
$$;

COMMENT ON FUNCTION app.caller_can_read_document(uuid, text, uuid) IS
  'Document ACL predicate shared by RPCs and RLS helpers.';

CREATE OR REPLACE FUNCTION app.list_visible_documents(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  id uuid,
  title text,
  visibility app.document_visibility,
  current_version_id uuid,
  visibility_generation bigint
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT
    d.id,
    d.title,
    d.visibility,
    d.current_version_id,
    d.visibility_generation
  FROM app.documents AS d
  WHERE app.validate_caller_context(
      caller_user_id,
      caller_role,
      caller_authorization_version
    )
    AND d.deleted_at IS NULL
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id);
$$;

COMMENT ON FUNCTION app.list_visible_documents(uuid, text, bigint) IS
  'Security-invoker document listing using explicit server-derived caller context.';

CREATE OR REPLACE FUNCTION app.list_user_conversations(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  id uuid,
  creator_user_id uuid,
  title text
)
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $$
  SELECT c.id, c.creator_user_id, c.title
  FROM app.conversations AS c
  WHERE app.validate_caller_context(
      caller_user_id,
      caller_role,
      caller_authorization_version
    )
    AND c.deleted_at IS NULL
    AND (
      c.creator_user_id = caller_user_id
      OR caller_role IN ('owner', 'admin')
    );
$$;

COMMENT ON FUNCTION app.list_user_conversations(uuid, text, bigint) IS
  'Creator-private conversations with owner/admin audit visibility via RPC context.';

CREATE OR REPLACE FUNCTION app.append_audit_event(
  p_event_type text,
  p_actor_user_id uuid,
  p_actor_role app.user_role,
  p_target_type text,
  p_target_id uuid,
  p_authorization_version bigint,
  p_payload jsonb DEFAULT '{}'::jsonb
)
RETURNS uuid
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  new_id uuid;
BEGIN
  INSERT INTO app.audit_events (
    event_type,
    actor_user_id,
    actor_role,
    target_type,
    target_id,
    authorization_version,
    payload
  )
  VALUES (
    p_event_type,
    p_actor_user_id,
    p_actor_role,
    p_target_type,
    p_target_id,
    p_authorization_version,
    COALESCE(p_payload, '{}'::jsonb)
  )
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.append_audit_event(text, uuid, app.user_role, text, uuid, bigint, jsonb) IS
  'Single append-only audit insert path for app_audit_writer.';

-- ---------------------------------------------------------------------------
-- Authorization atomicity triggers
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.bump_authorization_on_visibility_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.visibility IS DISTINCT FROM OLD.visibility
      OR NEW.deleted_at IS DISTINCT FROM OLD.deleted_at
      OR NEW.graph_eligible IS DISTINCT FROM OLD.graph_eligible THEN
      NEW.visibility_generation := OLD.visibility_generation + 1;

      UPDATE app.company_settings
      SET authorization_version = authorization_version + 1,
          visibility_generation = visibility_generation + 1,
          updated_at = timezone('utc', now())
      WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;

      INSERT INTO app.bm25_index_jobs (
        version_id,
        operation,
        priority,
        idempotency_key,
        payload_ref
      )
      SELECT
        NEW.current_version_id,
        CASE
          WHEN NEW.deleted_at IS NOT NULL THEN 'delete'::app.bm25_job_operation
          ELSE 'upsert'::app.bm25_job_operation
        END,
        CASE
          WHEN NEW.deleted_at IS NOT NULL THEN 'high'::app.job_priority
          ELSE 'normal'::app.job_priority
        END,
        format('visibility:%s:%s', NEW.id, NEW.visibility_generation),
        jsonb_build_object(
          'document_id', NEW.id,
          'reason', TG_OP,
          'visibility', NEW.visibility,
          'deleted_at', NEW.deleted_at
        )
      WHERE NEW.current_version_id IS NOT NULL;
    END IF;
  END IF;

  RETURN NEW;
END;
$fn$;

CREATE TRIGGER documents_bump_authorization_on_visibility
  BEFORE UPDATE OF visibility, deleted_at, graph_eligible ON app.documents
  FOR EACH ROW
  EXECUTE FUNCTION app.bump_authorization_on_visibility_change();

CREATE OR REPLACE FUNCTION app.bump_authorization_on_acl_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  target_document_id uuid;
BEGIN
  target_document_id := COALESCE(NEW.document_id, OLD.document_id);

  UPDATE app.company_settings
  SET authorization_version = authorization_version + 1,
      updated_at = timezone('utc', now())
  WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;

  UPDATE app.documents
  SET visibility_generation = visibility_generation + 1,
      updated_at = timezone('utc', now())
  WHERE id = target_document_id;

  INSERT INTO app.bm25_index_jobs (
    version_id,
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  SELECT
    d.current_version_id,
    'upsert'::app.bm25_job_operation,
    'high'::app.job_priority,
    format('acl:%s:%s', d.id, d.visibility_generation),
    jsonb_build_object('document_id', d.id, 'reason', 'document_acl_change')
  FROM app.documents AS d
  WHERE d.id = target_document_id
    AND d.current_version_id IS NOT NULL;

  RETURN COALESCE(NEW, OLD);
END;
$fn$;

CREATE TRIGGER document_acl_bump_authorization
  AFTER INSERT OR UPDATE OR DELETE ON app.document_acl
  FOR EACH ROW
  EXECUTE FUNCTION app.bump_authorization_on_acl_change();

CREATE OR REPLACE FUNCTION app.bump_authorization_on_profile_role_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'UPDATE' THEN
    IF NEW.role IS DISTINCT FROM OLD.role
      OR NEW.disabled_at IS DISTINCT FROM OLD.disabled_at
      OR NEW.upload_enabled IS DISTINCT FROM OLD.upload_enabled
      OR NEW.mfa_enrolled IS DISTINCT FROM OLD.mfa_enrolled THEN
      UPDATE app.company_settings
      SET authorization_version = authorization_version + 1,
          updated_at = timezone('utc', now())
      WHERE id = '00000000-0000-0000-0000-000000000001'::uuid;
    END IF;
  END IF;

  RETURN NEW;
END;
$fn$;

CREATE TRIGGER profiles_bump_authorization
  AFTER UPDATE OF role, disabled_at, upload_enabled, mfa_enrolled ON app.profiles
  FOR EACH ROW
  EXECUTE FUNCTION app.bump_authorization_on_profile_role_change();

CREATE OR REPLACE FUNCTION app.reject_restricted_graph_index_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc_visibility app.document_visibility;
  doc_deleted timestamptz;
  doc_graph_eligible boolean;
BEGIN
  IF NEW.operation IN ('index', 'rebuild') THEN
    SELECT d.visibility, d.deleted_at, d.graph_eligible
    INTO doc_visibility, doc_deleted, doc_graph_eligible
    FROM app.documents AS d
    WHERE d.id = NEW.document_id;

    IF doc_visibility = 'restricted'::app.document_visibility
      OR doc_deleted IS NOT NULL
      OR doc_graph_eligible = false THEN
      RAISE EXCEPTION
        'graph index job rejected: document must be current, company_visible, and graph_eligible';
    END IF;
  END IF;

  RETURN NEW;
END;
$fn$;

CREATE TRIGGER lightrag_index_jobs_reject_restricted
  BEFORE INSERT ON app.lightrag_index_jobs
  FOR EACH ROW
  EXECUTE FUNCTION app.reject_restricted_graph_index_job();

-- ---------------------------------------------------------------------------
-- Security-invoker health view
-- ---------------------------------------------------------------------------

CREATE OR REPLACE VIEW app.company_health
WITH (security_invoker = true) AS
SELECT
  cs.authorization_version,
  cs.visibility_generation,
  cs.default_document_visibility,
  cs.updated_at
FROM app.company_settings AS cs
WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid;

COMMENT ON VIEW app.company_health IS
  'Minimum health metadata for API role. security_invoker=true inherits caller RLS.';

-- ---------------------------------------------------------------------------
-- RLS policies
-- ---------------------------------------------------------------------------

CREATE POLICY profiles_select_own_or_admin
  ON app.profiles
  FOR SELECT
  TO authenticated
  USING (
    user_id = auth.uid()
    OR EXISTS (
      SELECT 1
      FROM app.profiles AS actor
      WHERE actor.user_id = auth.uid()
        AND actor.disabled_at IS NULL
        AND actor.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  );

CREATE POLICY profiles_update_self_non_role
  ON app.profiles
  FOR UPDATE
  TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (
    user_id = auth.uid()
    AND role = (
      SELECT p.role
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
    )
  );

CREATE POLICY company_settings_select_active_member
  ON app.company_settings
  FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
    )
  );

CREATE POLICY documents_select_member_acl
  ON app.documents
  FOR SELECT
  TO authenticated
  USING (
    deleted_at IS NULL
    AND EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
    )
    AND (
      visibility = 'company_visible'::app.document_visibility
      OR EXISTS (
        SELECT 1
        FROM app.profiles AS p
        WHERE p.user_id = auth.uid()
          AND p.disabled_at IS NULL
          AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
      )
      OR EXISTS (
        SELECT 1
        FROM app.document_acl AS acl
        WHERE acl.document_id = documents.id
          AND acl.grantee_user_id = auth.uid()
          AND acl.revoked_at IS NULL
      )
    )
  );

CREATE POLICY documents_mutate_owner_admin
  ON app.documents
  FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  );

CREATE POLICY document_acl_select_grantee_or_admin
  ON app.document_acl
  FOR SELECT
  TO authenticated
  USING (
    grantee_user_id = auth.uid()
    OR EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  );

CREATE POLICY document_acl_mutate_owner_admin
  ON app.document_acl
  FOR ALL
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  )
  WITH CHECK (
    EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  );

CREATE POLICY conversations_creator_private
  ON app.conversations
  FOR SELECT
  TO authenticated
  USING (
    deleted_at IS NULL
    AND (
      creator_user_id = auth.uid()
      OR EXISTS (
        SELECT 1
        FROM app.profiles AS p
        WHERE p.user_id = auth.uid()
          AND p.disabled_at IS NULL
          AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
      )
    )
  );

CREATE POLICY conversations_insert_creator
  ON app.conversations
  FOR INSERT
  TO authenticated
  WITH CHECK (creator_user_id = auth.uid());

CREATE POLICY conversations_update_creator
  ON app.conversations
  FOR UPDATE
  TO authenticated
  USING (creator_user_id = auth.uid())
  WITH CHECK (creator_user_id = auth.uid());

CREATE POLICY messages_select_via_conversation
  ON app.messages
  FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM app.conversations AS c
      WHERE c.id = messages.conversation_id
        AND c.deleted_at IS NULL
        AND (
          c.creator_user_id = auth.uid()
          OR EXISTS (
            SELECT 1
            FROM app.profiles AS p
            WHERE p.user_id = auth.uid()
              AND p.disabled_at IS NULL
              AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
          )
        )
    )
  );

CREATE POLICY runs_creator_private
  ON app.runs
  FOR SELECT
  TO authenticated
  USING (
    creator_user_id = auth.uid()
    OR EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  );

CREATE POLICY tool_catalog_select_active_member
  ON app.tool_catalog
  FOR SELECT
  TO authenticated
  USING (
    active = true
    AND EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
    )
  );

CREATE POLICY tool_permissions_select_self_or_admin
  ON app.tool_permissions
  FOR SELECT
  TO authenticated
  USING (
    user_id = auth.uid()
    OR EXISTS (
      SELECT 1
      FROM app.profiles AS p
      WHERE p.user_id = auth.uid()
        AND p.disabled_at IS NULL
        AND p.role IN ('owner'::app.user_role, 'admin'::app.user_role)
    )
  );

-- Runtime role policies (defense in depth when grants exist)

CREATE POLICY documents_worker_rw
  ON app.documents
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY document_versions_worker_rw
  ON app.document_versions
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY document_chunks_worker_rw
  ON app.document_chunks
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY ingestion_jobs_worker_rw
  ON app.ingestion_jobs
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY bm25_index_jobs_worker_rw
  ON app.bm25_index_jobs
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY lightrag_index_jobs_worker_rw
  ON app.lightrag_index_jobs
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

CREATE POLICY company_settings_api_health
  ON app.company_settings
  FOR SELECT
  TO app_api
  USING (id = '00000000-0000-0000-0000-000000000001'::uuid);

CREATE POLICY profiles_api_validate
  ON app.profiles
  FOR SELECT
  TO app_api
  USING (true);

CREATE POLICY documents_api_rpc_read
  ON app.documents
  FOR SELECT
  TO app_api
  USING (deleted_at IS NULL);

CREATE POLICY document_acl_api_rpc_read
  ON app.document_acl
  FOR SELECT
  TO app_api
  USING (revoked_at IS NULL);

CREATE POLICY conversations_api_rpc_read
  ON app.conversations
  FOR SELECT
  TO app_api
  USING (deleted_at IS NULL);

CREATE POLICY audit_events_audit_writer_insert
  ON app.audit_events
  FOR INSERT
  TO app_audit_writer
  WITH CHECK (false);

CREATE POLICY langgraph_checkpointer_all
  ON langgraph.checkpoints
  FOR ALL
  TO app_checkpointer
  USING (true)
  WITH CHECK (true);

CREATE POLICY langgraph_blobs_checkpointer_all
  ON langgraph.checkpoint_blobs
  FOR ALL
  TO app_checkpointer
  USING (true)
  WITH CHECK (true);

CREATE POLICY langgraph_writes_checkpointer_all
  ON langgraph.checkpoint_writes
  FOR ALL
  TO app_checkpointer
  USING (true)
  WITH CHECK (true);

CREATE POLICY langgraph_migrations_checkpointer_all
  ON langgraph.checkpoint_migrations
  FOR ALL
  TO app_checkpointer
  USING (true)
  WITH CHECK (true);

CREATE POLICY lightrag_capture_status_rw
  ON lightrag.schema_capture_status
  FOR ALL
  TO app_lightrag
  USING (true)
  WITH CHECK (true);

-- Force RLS on canonical evidence and private schemas
ALTER TABLE app.profiles FORCE ROW LEVEL SECURITY;
ALTER TABLE app.company_settings FORCE ROW LEVEL SECURITY;
ALTER TABLE app.documents FORCE ROW LEVEL SECURITY;
ALTER TABLE app.document_acl FORCE ROW LEVEL SECURITY;
ALTER TABLE app.conversations FORCE ROW LEVEL SECURITY;
ALTER TABLE app.messages FORCE ROW LEVEL SECURITY;
ALTER TABLE app.runs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.audit_events FORCE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoints FORCE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoint_blobs FORCE ROW LEVEL SECURITY;
ALTER TABLE langgraph.checkpoint_writes FORCE ROW LEVEL SECURITY;
ALTER TABLE lightrag.schema_capture_status FORCE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Revoke browser/runtime excess; grant least privilege
-- ---------------------------------------------------------------------------

REVOKE ALL ON SCHEMA app FROM anon, authenticated;
REVOKE ALL ON SCHEMA private FROM anon, authenticated;
REVOKE ALL ON SCHEMA langgraph FROM anon, authenticated;
REVOKE ALL ON SCHEMA lightrag FROM anon, authenticated;

REVOKE ALL ON ALL TABLES IN SCHEMA app FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA private FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA langgraph FROM anon, authenticated;
REVOKE ALL ON ALL TABLES IN SCHEMA lightrag FROM anon, authenticated;

REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA private FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA langgraph FROM anon, authenticated;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA lightrag FROM anon, authenticated;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app FROM anon, authenticated;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA private FROM anon, authenticated;

REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;
REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA private FROM PUBLIC;

-- app_api: RPC + minimum health metadata
GRANT USAGE ON SCHEMA app TO app_api;
GRANT SELECT ON app.company_settings TO app_api;
GRANT SELECT ON app.profiles TO app_api;
GRANT SELECT ON app.documents TO app_api;
GRANT SELECT ON app.document_acl TO app_api;
GRANT SELECT ON app.conversations TO app_api;
GRANT SELECT ON app.company_health TO app_api;
GRANT EXECUTE ON FUNCTION app.current_authorization_version() TO app_api;
GRANT EXECUTE ON FUNCTION app.validate_caller_context(uuid, text, bigint) TO app_api;
GRANT EXECUTE ON FUNCTION app.caller_can_read_document(uuid, text, uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.list_visible_documents(uuid, text, bigint) TO app_api;
GRANT EXECUTE ON FUNCTION app.list_user_conversations(uuid, text, bigint) TO app_api;

-- app_worker: jobs + canonical ingestion writes (no conversations)
GRANT USAGE ON SCHEMA app TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.documents TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.document_versions TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.document_chunks TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.document_sources TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.document_search_terms TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.search_aliases TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.document_tables TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.document_table_columns TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.ingestion_jobs TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.bm25_index_jobs TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.bm25_index_versions TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.lightrag_index_jobs TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.lightrag_source_map TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.lightrag_chunk_map TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.graph_evidence_map TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.graph_entity_rules TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.dead_letter_jobs TO app_worker;

-- app_checkpointer: langgraph only
GRANT USAGE ON SCHEMA langgraph TO app_checkpointer;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA langgraph TO app_checkpointer;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA langgraph TO app_checkpointer;

-- app_lightrag: lightrag only
GRANT USAGE ON SCHEMA lightrag TO app_lightrag;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lightrag TO app_lightrag;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA lightrag TO app_lightrag;

-- app_audit_writer: append-only via controlled function (no direct table DML)
GRANT USAGE ON SCHEMA app TO app_audit_writer;
REVOKE ALL ON app.audit_events FROM app_audit_writer;
GRANT EXECUTE ON FUNCTION app.append_audit_event(
  text,
  uuid,
  app.user_role,
  text,
  uuid,
  bigint,
  jsonb
) TO app_audit_writer;

-- Local GRANT testing: allow postgres superuser to SET ROLE
GRANT app_api TO postgres;
GRANT app_worker TO postgres;
GRANT app_checkpointer TO postgres;
GRANT app_lightrag TO postgres;
GRANT app_audit_writer TO postgres;

ALTER DEFAULT PRIVILEGES IN SCHEMA app REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA private REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
