-- Phase 2 Packet 6: role timeouts/work_mem/application_name, hash-chained audit,
-- payload redaction, and verify_audit_chain.

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

-- ---------------------------------------------------------------------------
-- Expand audit_events for hash chain + purpose/resource identifiers
-- ---------------------------------------------------------------------------

ALTER TABLE app.audit_events
  ADD COLUMN IF NOT EXISTS event_hash text,
  ADD COLUMN IF NOT EXISTS previous_hash text,
  ADD COLUMN IF NOT EXISTS purpose text,
  ADD COLUMN IF NOT EXISTS resource_type text,
  ADD COLUMN IF NOT EXISTS resource_id uuid,
  ADD COLUMN IF NOT EXISTS chain_seq bigint;

CREATE SEQUENCE IF NOT EXISTS app.audit_events_chain_seq AS bigint;

ALTER TABLE app.audit_events
  ALTER COLUMN chain_seq SET DEFAULT nextval('app.audit_events_chain_seq');

ALTER SEQUENCE app.audit_events_chain_seq OWNED BY app.audit_events.chain_seq;

COMMENT ON COLUMN app.audit_events.event_hash IS
  'SHA-256 hex digest of canonical event fields plus previous_hash.';
COMMENT ON COLUMN app.audit_events.previous_hash IS
  'Prior event_hash in chain_seq order; genesis uses 64 zero hex digits.';
COMMENT ON COLUMN app.audit_events.purpose IS
  'Short purpose label for restricted-read / admin actions.';
COMMENT ON COLUMN app.audit_events.resource_type IS
  'Optional resource class (document, conversation, invitation, …).';
COMMENT ON COLUMN app.audit_events.resource_id IS
  'Optional resource UUID when distinct from target_id.';
COMMENT ON COLUMN app.audit_events.chain_seq IS
  'Monotonic insertion order for hash-chain linking (avoids UUID/created_at races).';

CREATE UNIQUE INDEX IF NOT EXISTS audit_events_chain_seq_uidx
  ON app.audit_events (chain_seq);

-- ---------------------------------------------------------------------------
-- Role timeouts, work_mem, and query tags (application_name)
-- Values match docs/architecture/05-database-connections.md and 06-*.md.
-- ---------------------------------------------------------------------------

ALTER ROLE app_api SET statement_timeout = '15s';
ALTER ROLE app_api SET lock_timeout = '2s';
ALTER ROLE app_api SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE app_api SET work_mem = '8MB';
ALTER ROLE app_api SET application_name = 'smart-rag-api';

ALTER ROLE app_worker SET statement_timeout = '60s';
ALTER ROLE app_worker SET lock_timeout = '5s';
ALTER ROLE app_worker SET idle_in_transaction_session_timeout = '15s';
ALTER ROLE app_worker SET work_mem = '16MB';
ALTER ROLE app_worker SET application_name = 'smart-rag-worker';

ALTER ROLE app_checkpointer SET statement_timeout = '30s';
ALTER ROLE app_checkpointer SET lock_timeout = '3s';
ALTER ROLE app_checkpointer SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE app_checkpointer SET work_mem = '16MB';
ALTER ROLE app_checkpointer SET application_name = 'smart-rag-checkpointer';

ALTER ROLE app_lightrag SET statement_timeout = '120s';
ALTER ROLE app_lightrag SET lock_timeout = '5s';
ALTER ROLE app_lightrag SET idle_in_transaction_session_timeout = '30s';
ALTER ROLE app_lightrag SET work_mem = '16MB';
ALTER ROLE app_lightrag SET application_name = 'smart-rag-lightrag';

ALTER ROLE app_audit_writer SET statement_timeout = '15s';
ALTER ROLE app_audit_writer SET lock_timeout = '2s';
ALTER ROLE app_audit_writer SET idle_in_transaction_session_timeout = '5s';
ALTER ROLE app_audit_writer SET work_mem = '8MB';
ALTER ROLE app_audit_writer SET application_name = 'smart-rag-audit';

-- ---------------------------------------------------------------------------
-- Payload redaction (sensitive key substrings)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.redact_audit_payload(payload jsonb)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
STRICT
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  result jsonb := '{}'::jsonb;
  key text;
  value jsonb;
  lower_key text;
BEGIN
  IF payload IS NULL OR jsonb_typeof(payload) <> 'object' THEN
    RETURN COALESCE(payload, '{}'::jsonb);
  END IF;

  FOR key, value IN SELECT * FROM jsonb_each(payload)
  LOOP
    lower_key := lower(key);
    IF lower_key LIKE '%password%'
      OR lower_key LIKE '%token%'
      OR lower_key LIKE '%secret%'
      OR lower_key LIKE '%raw_ip%'
      OR lower_key = 'raw_ip' THEN
      result := result || jsonb_build_object(key, '[REDACTED]');
    ELSIF jsonb_typeof(value) = 'object' THEN
      result := result || jsonb_build_object(key, app.redact_audit_payload(value));
    ELSIF jsonb_typeof(value) = 'array' THEN
      result := result || jsonb_build_object(
        key,
        (
          SELECT COALESCE(jsonb_agg(
            CASE
              WHEN jsonb_typeof(elem) = 'object' THEN app.redact_audit_payload(elem)
              ELSE elem
            END
          ), '[]'::jsonb)
          FROM jsonb_array_elements(value) AS elem
        )
      );
    ELSE
      result := result || jsonb_build_object(key, value);
    END IF;
  END LOOP;

  RETURN result;
END;
$fn$;

COMMENT ON FUNCTION app.redact_audit_payload(jsonb) IS
  'Strips password/token/secret/raw_ip keys from audit payloads before hashing.';

REVOKE ALL ON FUNCTION app.redact_audit_payload(jsonb) FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Canonical hash material + BEFORE INSERT chain trigger
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.audit_event_canonical_material(
  p_event_type text,
  p_actor_user_id uuid,
  p_actor_role app.user_role,
  p_target_type text,
  p_target_id uuid,
  p_authorization_version bigint,
  p_visibility_generation bigint,
  p_session_id text,
  p_purpose text,
  p_resource_type text,
  p_resource_id uuid,
  p_payload jsonb,
  p_previous_hash text,
  p_created_at timestamptz
)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, app
AS $$
  SELECT jsonb_strip_nulls(
    jsonb_build_object(
      'event_type', p_event_type,
      'actor_user_id', p_actor_user_id,
      'actor_role', p_actor_role,
      'target_type', p_target_type,
      'target_id', p_target_id,
      'authorization_version', p_authorization_version,
      'visibility_generation', p_visibility_generation,
      'session_id', p_session_id,
      'purpose', p_purpose,
      'resource_type', p_resource_type,
      'resource_id', p_resource_id,
      'payload', COALESCE(p_payload, '{}'::jsonb),
      'previous_hash', p_previous_hash,
      'created_at', p_created_at
    )
  )::text;
$$;

COMMENT ON FUNCTION app.audit_event_canonical_material(
  text, uuid, app.user_role, text, uuid, bigint, bigint, text, text, text, uuid, jsonb, text, timestamptz
) IS
  'Deterministic JSON text hashed into audit_events.event_hash.';

REVOKE ALL ON FUNCTION app.audit_event_canonical_material(
  text, uuid, app.user_role, text, uuid, bigint, bigint, text, text, text, uuid, jsonb, text, timestamptz
) FROM PUBLIC;

CREATE OR REPLACE FUNCTION app.audit_events_hash_chain_bi()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, extensions, app
AS $fn$
DECLARE
  genesis constant text :=
    '0000000000000000000000000000000000000000000000000000000000000000';
  prior_hash text;
BEGIN
  NEW.payload := app.redact_audit_payload(COALESCE(NEW.payload, '{}'::jsonb));

  IF NEW.created_at IS NULL THEN
    NEW.created_at := timezone('utc', now());
  END IF;

  IF NEW.chain_seq IS NULL THEN
    NEW.chain_seq := nextval('app.audit_events_chain_seq');
  END IF;

  SELECT ae.event_hash
  INTO prior_hash
  FROM app.audit_events AS ae
  ORDER BY ae.chain_seq DESC NULLS LAST
  LIMIT 1;

  NEW.previous_hash := COALESCE(prior_hash, genesis);
  NEW.event_hash := encode(
    digest(
      convert_to(
        app.audit_event_canonical_material(
          NEW.event_type,
          NEW.actor_user_id,
          NEW.actor_role,
          NEW.target_type,
          NEW.target_id,
          NEW.authorization_version,
          NEW.visibility_generation,
          NEW.session_id,
          NEW.purpose,
          NEW.resource_type,
          NEW.resource_id,
          NEW.payload,
          NEW.previous_hash,
          NEW.created_at
        ),
        'UTF8'
      ),
      'sha256'
    ),
    'hex'
  );

  RETURN NEW;
END;
$fn$;

COMMENT ON FUNCTION app.audit_events_hash_chain_bi() IS
  'BEFORE INSERT: redact payload, link previous_hash, compute SHA-256 event_hash.';

DROP TRIGGER IF EXISTS audit_events_hash_chain_bi ON app.audit_events;
CREATE TRIGGER audit_events_hash_chain_bi
  BEFORE INSERT ON app.audit_events
  FOR EACH ROW
  EXECUTE FUNCTION app.audit_events_hash_chain_bi();

-- ---------------------------------------------------------------------------
-- Controlled append path (replaces Packet 3 signature with additive params)
-- ---------------------------------------------------------------------------

DROP FUNCTION IF EXISTS app.append_audit_event(
  text, uuid, app.user_role, text, uuid, bigint, jsonb
);

CREATE OR REPLACE FUNCTION app.append_audit_event(
  p_event_type text,
  p_actor_user_id uuid,
  p_actor_role app.user_role,
  p_target_type text,
  p_target_id uuid,
  p_authorization_version bigint,
  p_payload jsonb DEFAULT '{}'::jsonb,
  p_purpose text DEFAULT NULL,
  p_resource_type text DEFAULT NULL,
  p_resource_id uuid DEFAULT NULL,
  p_session_id text DEFAULT NULL
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
    session_id,
    purpose,
    resource_type,
    resource_id,
    payload
  )
  VALUES (
    p_event_type,
    p_actor_user_id,
    p_actor_role,
    p_target_type,
    p_target_id,
    p_authorization_version,
    p_session_id,
    p_purpose,
    p_resource_type,
    p_resource_id,
    COALESCE(p_payload, '{}'::jsonb)
  )
  RETURNING id INTO new_id;

  RETURN new_id;
END;
$fn$;

COMMENT ON FUNCTION app.append_audit_event(
  text, uuid, app.user_role, text, uuid, bigint, jsonb, text, text, uuid, text
) IS
  'Privileged append-only insert; hash chain + redaction applied by trigger.';

REVOKE ALL ON FUNCTION app.append_audit_event(
  text, uuid, app.user_role, text, uuid, bigint, jsonb, text, text, uuid, text
) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.append_audit_event(
  text, uuid, app.user_role, text, uuid, bigint, jsonb, text, text, uuid, text
) TO app_audit_writer;

GRANT EXECUTE ON FUNCTION app.append_audit_event(
  text, uuid, app.user_role, text, uuid, bigint, jsonb, text, text, uuid, text
) TO app_api;

-- ---------------------------------------------------------------------------
-- Tamper detection: walk chain and return first broken id (or NULL)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION app.verify_audit_chain(limit_n integer DEFAULT 1000)
RETURNS uuid
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, extensions, app
AS $fn$
DECLARE
  genesis constant text :=
    '0000000000000000000000000000000000000000000000000000000000000000';
  rec record;
  expected_prev text := genesis;
  expected_hash text;
  scanned integer := 0;
  max_n integer := GREATEST(COALESCE(limit_n, 1000), 1);
BEGIN
  FOR rec IN
    SELECT
      ae.id,
      ae.event_type,
      ae.actor_user_id,
      ae.actor_role,
      ae.target_type,
      ae.target_id,
      ae.authorization_version,
      ae.visibility_generation,
      ae.session_id,
      ae.purpose,
      ae.resource_type,
      ae.resource_id,
      ae.payload,
      ae.previous_hash,
      ae.event_hash,
      ae.created_at
    FROM app.audit_events AS ae
    ORDER BY ae.chain_seq ASC NULLS LAST
    LIMIT max_n
  LOOP
    scanned := scanned + 1;

    IF rec.previous_hash IS DISTINCT FROM expected_prev THEN
      RETURN rec.id;
    END IF;

    expected_hash := encode(
      digest(
        convert_to(
          app.audit_event_canonical_material(
            rec.event_type,
            rec.actor_user_id,
            rec.actor_role,
            rec.target_type,
            rec.target_id,
            rec.authorization_version,
            rec.visibility_generation,
            rec.session_id,
            rec.purpose,
            rec.resource_type,
            rec.resource_id,
            rec.payload,
            rec.previous_hash,
            rec.created_at
          ),
          'UTF8'
        ),
        'sha256'
      ),
      'hex'
    );

    IF rec.event_hash IS DISTINCT FROM expected_hash THEN
      RETURN rec.id;
    END IF;

    expected_prev := rec.event_hash;
  END LOOP;

  RETURN NULL;
END;
$fn$;

COMMENT ON FUNCTION app.verify_audit_chain(integer) IS
  'Returns first broken audit event id within the scanned window, or NULL if intact.';

REVOKE ALL ON FUNCTION app.verify_audit_chain(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.verify_audit_chain(integer) TO app_api;
