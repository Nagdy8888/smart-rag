-- Phase 2 Packet 2: documents, versions, sources, ACL, approvals, scan events.

CREATE TABLE app.documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  title text NOT NULL,
  description text,
  visibility app.document_visibility NOT NULL DEFAULT 'company_visible',
  current_version_id uuid,
  visibility_generation bigint NOT NULL DEFAULT 1,
  graph_eligible boolean NOT NULL DEFAULT false,
  created_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT documents_graph_eligible_requires_company_visible CHECK (
    graph_eligible = false
    OR (
      visibility = 'company_visible'
      AND current_version_id IS NOT NULL
      AND deleted_at IS NULL
    )
  )
);

COMMENT ON TABLE app.documents IS
  'Canonical document shell. current_version_id is the single visibility pointer.';

CREATE TABLE app.document_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_number integer NOT NULL,
  status app.document_status NOT NULL DEFAULT 'uploaded',
  storage_bucket text,
  storage_path text,
  content_hash text,
  media_type text,
  byte_size bigint,
  effective_at timestamptz,
  language text,
  graph_eligible boolean NOT NULL DEFAULT false,
  deleted_at timestamptz,
  created_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT document_versions_version_positive CHECK (version_number > 0),
  CONSTRAINT document_versions_graph_eligible_requires_open CHECK (
    graph_eligible = false OR deleted_at IS NULL
  ),
  CONSTRAINT document_versions_unique_number UNIQUE (document_id, version_number)
);

ALTER TABLE app.documents
  ADD CONSTRAINT documents_current_version_id_fkey
  FOREIGN KEY (current_version_id) REFERENCES app.document_versions (id)
  ON DELETE RESTRICT;

CREATE TABLE app.document_sources (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE SET NULL,
  source_type app.source_type NOT NULL,
  source_uri text,
  declared_category text,
  approval_required boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE app.document_acl (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  grantee_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  granted_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE UNIQUE INDEX document_acl_active_grant_uq
  ON app.document_acl (document_id, grantee_user_id)
  WHERE revoked_at IS NULL;

COMMENT ON TABLE app.document_acl IS
  'Per-user restricted grants only. No groups or role-wide restricted grants in v1.';

CREATE TABLE app.source_approval_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid REFERENCES app.document_sources (id) ON DELETE CASCADE,
  requested_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  reviewed_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  status app.approval_status NOT NULL DEFAULT 'pending',
  domain text,
  start_url text,
  review_notes text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE app.document_scan_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE CASCADE,
  scan_engine_version text,
  signature_version text,
  result app.scan_result NOT NULL,
  object_hash text,
  scanned_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  details jsonb NOT NULL DEFAULT '{}'::jsonb
);

COMMENT ON TABLE app.document_scan_events IS
  'Append-only scan provenance. Phase 3 ingestion writes events; no UPDATE path required.';

CREATE OR REPLACE FUNCTION app.enforce_document_current_version()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_document_id uuid;
BEGIN
  IF NEW.current_version_id IS NULL THEN
    RETURN NEW;
  END IF;

  SELECT dv.document_id
  INTO version_document_id
  FROM app.document_versions AS dv
  WHERE dv.id = NEW.current_version_id;

  IF version_document_id IS NULL THEN
    RAISE EXCEPTION 'current_version_id % does not exist', NEW.current_version_id;
  END IF;

  IF version_document_id IS DISTINCT FROM NEW.id THEN
    RAISE EXCEPTION
      'current_version_id % belongs to document %, not %',
      NEW.current_version_id,
      version_document_id,
      NEW.id;
  END IF;

  RETURN NEW;
END;
$fn$;

CREATE TRIGGER documents_enforce_current_version
  BEFORE INSERT OR UPDATE OF current_version_id ON app.documents
  FOR EACH ROW
  EXECUTE FUNCTION app.enforce_document_current_version();

CREATE TRIGGER documents_touch_updated_at
  BEFORE UPDATE ON app.documents
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER document_versions_touch_updated_at
  BEFORE UPDATE ON app.document_versions
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER document_sources_touch_updated_at
  BEFORE UPDATE ON app.document_sources
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER document_acl_touch_updated_at
  BEFORE UPDATE ON app.document_acl
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER source_approval_requests_touch_updated_at
  BEFORE UPDATE ON app.source_approval_requests
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
