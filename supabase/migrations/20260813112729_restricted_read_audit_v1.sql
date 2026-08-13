-- Phase 2 Packet 5 remediation: authorized restricted-read audit admission.

CREATE OR REPLACE FUNCTION app.block_restricted_read_event_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $fn$
BEGIN
  RAISE EXCEPTION 'restricted_read_events is append-only';
END;
$fn$;

CREATE TRIGGER restricted_read_events_block_mutation
  BEFORE UPDATE OR DELETE ON app.restricted_read_events
  FOR EACH ROW
  EXECUTE FUNCTION app.block_restricted_read_event_mutation();

ALTER TABLE app.restricted_read_events FORCE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION app.authorize_restricted_read(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid,
  p_version_id uuid,
  p_purpose text,
  p_session_id text,
  p_signed_url_expires_at timestamptz DEFAULT NULL
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  document_row app.documents%ROWTYPE;
  audit_id uuid;
  restricted_read_id uuid;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  IF p_purpose NOT IN ('evidence', 'preview', 'download') THEN
    RAISE EXCEPTION 'restricted read purpose rejected';
  END IF;

  IF p_session_id IS NULL
    OR btrim(p_session_id) = ''
    OR char_length(p_session_id) > 256 THEN
    RAISE EXCEPTION 'bounded session identifier required';
  END IF;

  IF p_purpose = 'download' THEN
    IF p_signed_url_expires_at IS NULL
      OR p_signed_url_expires_at <= timezone('utc', now()) THEN
      RAISE EXCEPTION 'download expiry must be in the future';
    END IF;
  ELSIF p_signed_url_expires_at IS NOT NULL THEN
    RAISE EXCEPTION 'signed URL expiry is valid only for download';
  END IF;

  SELECT document.*
  INTO document_row
  FROM app.documents AS document
  WHERE document.id = p_document_id
  FOR SHARE;

  IF NOT FOUND
    OR document_row.deleted_at IS NOT NULL
    OR document_row.visibility IS DISTINCT FROM 'restricted'::app.document_visibility
    OR document_row.current_version_id IS DISTINCT FROM p_version_id THEN
    RAISE EXCEPTION 'active restricted current version not found';
  END IF;

  IF NOT app.caller_can_read_document(
    caller_user_id,
    caller_role,
    p_document_id
  ) THEN
    RAISE EXCEPTION 'restricted read denied';
  END IF;

  audit_id := app.append_audit_event(
    'restricted_read.authorized',
    caller_user_id,
    caller_role::app.user_role,
    'document',
    p_document_id,
    app.current_authorization_version(),
    jsonb_build_object(
      'access_surface', p_purpose,
      'version_id', p_version_id
    ),
    p_purpose,
    'document_version',
    p_version_id,
    p_session_id
  );

  INSERT INTO app.restricted_read_events (
    audit_event_id,
    actor_user_id,
    document_id,
    version_id,
    purpose,
    signed_url_expires_at
  )
  VALUES (
    audit_id,
    caller_user_id,
    p_document_id,
    p_version_id,
    p_purpose,
    p_signed_url_expires_at
  )
  RETURNING id INTO restricted_read_id;

  RETURN restricted_read_id;
END;
$fn$;

COMMENT ON FUNCTION app.authorize_restricted_read(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  text,
  text,
  timestamptz
) IS
  'Authorizes one restricted evidence/preview/download access and atomically appends content-free audit records.';

REVOKE ALL ON FUNCTION app.block_restricted_read_event_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION app.authorize_restricted_read(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  text,
  text,
  timestamptz
) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.authorize_restricted_read(
  uuid,
  text,
  bigint,
  uuid,
  uuid,
  text,
  text,
  timestamptz
) TO app_api;
