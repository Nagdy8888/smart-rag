-- Phase 2 Packet 2: append-only audit chain, restricted reads, admin notifications.

CREATE TABLE app.audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_type text NOT NULL,
  actor_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  actor_role app.user_role,
  target_type text,
  target_id uuid,
  authorization_version bigint,
  visibility_generation bigint,
  session_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE app.audit_events IS
  'Append-only security/operations ledger. UPDATE/DELETE blocked by trigger.';

CREATE OR REPLACE FUNCTION app.block_audit_events_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RAISE EXCEPTION 'audit_events is append-only';
END;
$fn$;

CREATE TRIGGER audit_events_block_update
  BEFORE UPDATE ON app.audit_events
  FOR EACH ROW
  EXECUTE FUNCTION app.block_audit_events_mutation();

CREATE TRIGGER audit_events_block_delete
  BEFORE DELETE ON app.audit_events
  FOR EACH ROW
  EXECUTE FUNCTION app.block_audit_events_mutation();

CREATE TABLE app.audit_chain_anchors (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  anchor_date date NOT NULL,
  event_count bigint NOT NULL,
  chain_hash text NOT NULL,
  anchored_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  export_uri text,
  CONSTRAINT audit_chain_anchors_unique_date UNIQUE (anchor_date)
);

CREATE TABLE app.restricted_read_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  audit_event_id uuid REFERENCES app.audit_events (id) ON DELETE RESTRICT,
  actor_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  document_id uuid REFERENCES app.documents (id) ON DELETE SET NULL,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE SET NULL,
  run_id uuid REFERENCES app.runs (id) ON DELETE SET NULL,
  purpose text NOT NULL,
  signed_url_expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE app.restricted_read_events IS
  'Restricted evidence/preview/download auditing without storing passage text.';

CREATE TABLE app.admin_notifications (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  notification_kind text NOT NULL,
  severity text NOT NULL DEFAULT 'warning',
  title text NOT NULL,
  body text NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  acknowledged_at timestamptz,
  acknowledged_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);
