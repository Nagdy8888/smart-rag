-- Overlay Packet 2: append-only detector findings and hash-bound reviews.
-- Findings never store raw matched secrets. payload_ref.review_approved is
-- not an approval source.

CREATE TYPE app.detector_review_decision AS ENUM (
  'false_positive',
  'upheld',
  'rejected'
);

CREATE TABLE app.detector_findings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  content_hash text NOT NULL,
  scan_evidence_id uuid NOT NULL REFERENCES app.document_scan_events (id) ON DELETE RESTRICT,
  attestation_policy_version text NOT NULL,
  detector_policy_version text NOT NULL,
  detector_family text NOT NULL,
  finding_scope text NOT NULL,
  bounded_count integer NOT NULL,
  locator_fingerprint text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT detector_findings_scope_chk CHECK (
    finding_scope IN ('metadata', 'extraction')
  ),
  CONSTRAINT detector_findings_count_chk CHECK (
    bounded_count >= 1 AND bounded_count <= 100
  ),
  CONSTRAINT detector_findings_family_chk CHECK (
    detector_family IN ('payment_card', 'credentials', 'national_id', 'health')
  )
);

COMMENT ON TABLE app.detector_findings IS
  'Worker-authored detector hits. Fingerprints only; no raw matched secrets.';

CREATE INDEX detector_findings_version_hash_idx
  ON app.detector_findings (version_id, content_hash, detector_policy_version);

CREATE OR REPLACE FUNCTION app.block_detector_findings_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RAISE EXCEPTION 'detector_findings is append-only';
END;
$fn$;

CREATE TRIGGER detector_findings_block_update
  BEFORE UPDATE ON app.detector_findings
  FOR EACH ROW
  EXECUTE FUNCTION app.block_detector_findings_mutation();

CREATE TRIGGER detector_findings_block_delete
  BEFORE DELETE ON app.detector_findings
  FOR EACH ROW
  EXECUTE FUNCTION app.block_detector_findings_mutation();

CREATE TABLE app.detector_finding_reviews (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  finding_id uuid NOT NULL REFERENCES app.detector_findings (id) ON DELETE RESTRICT,
  actor_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE RESTRICT,
  actor_role app.user_role NOT NULL,
  authorization_version bigint,
  decision app.detector_review_decision NOT NULL,
  reason text NOT NULL,
  idempotency_key text NOT NULL,
  superseded_by uuid REFERENCES app.detector_finding_reviews (id),
  audit_event_id uuid REFERENCES app.audit_events (id) ON DELETE RESTRICT,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT detector_finding_reviews_reason_chk CHECK (char_length(reason) BETWEEN 1 AND 500),
  CONSTRAINT detector_finding_reviews_idempotency_uq UNIQUE (finding_id, idempotency_key)
);

COMMENT ON TABLE app.detector_finding_reviews IS
  'Owner/admin false-positive or uphold decisions. Active only while hash/scan/policy match.';

CREATE OR REPLACE FUNCTION app.block_detector_finding_reviews_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'detector_finding_reviews is append-only';
  END IF;
  IF NEW.finding_id IS DISTINCT FROM OLD.finding_id
     OR NEW.actor_user_id IS DISTINCT FROM OLD.actor_user_id
     OR NEW.decision IS DISTINCT FROM OLD.decision
     OR NEW.reason IS DISTINCT FROM OLD.reason
     OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
  THEN
    RAISE EXCEPTION 'detector_finding_reviews is append-only';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE TRIGGER detector_finding_reviews_block_update
  BEFORE UPDATE ON app.detector_finding_reviews
  FOR EACH ROW
  EXECUTE FUNCTION app.block_detector_finding_reviews_mutation();

CREATE TRIGGER detector_finding_reviews_block_delete
  BEFORE DELETE ON app.detector_finding_reviews
  FOR EACH ROW
  EXECUTE FUNCTION app.block_detector_finding_reviews_mutation();

CREATE OR REPLACE FUNCTION app.supersede_prior_detector_reviews()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  UPDATE app.detector_finding_reviews
  SET superseded_by = NEW.id
  WHERE finding_id = NEW.finding_id
    AND id IS DISTINCT FROM NEW.id
    AND superseded_by IS NULL;
  RETURN NEW;
END;
$fn$;

CREATE TRIGGER detector_finding_reviews_supersede_prior
  AFTER INSERT ON app.detector_finding_reviews
  FOR EACH ROW
  EXECUTE FUNCTION app.supersede_prior_detector_reviews();

ALTER TABLE app.detector_findings ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.detector_finding_reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY detector_findings_worker_insert
  ON app.detector_findings
  FOR INSERT
  TO app_worker
  WITH CHECK (true);

CREATE POLICY detector_findings_worker_select
  ON app.detector_findings
  FOR SELECT
  TO app_worker
  USING (true);

CREATE POLICY detector_findings_api_select
  ON app.detector_findings
  FOR SELECT
  TO app_api
  USING (false);

CREATE POLICY detector_finding_reviews_worker_select
  ON app.detector_finding_reviews
  FOR SELECT
  TO app_worker
  USING (true);

GRANT SELECT, INSERT ON app.detector_findings TO app_worker;
GRANT SELECT ON app.detector_finding_reviews TO app_worker;
GRANT SELECT ON app.detector_findings TO app_api;
GRANT SELECT, INSERT, UPDATE ON app.detector_finding_reviews TO app_api;

CREATE OR REPLACE FUNCTION app.review_detector_finding(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_finding_id uuid,
  p_decision text,
  p_reason text,
  p_idempotency_key text
)
RETURNS TABLE (
  review_id uuid,
  finding_id uuid,
  decision text,
  replayed boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_role app.user_role;
  v_document_id uuid;
  v_existing uuid;
  v_audit uuid;
  v_decision app.detector_review_decision;
BEGIN
  IF p_finding_id IS NULL OR p_idempotency_key IS NULL OR btrim(p_idempotency_key) = '' THEN
    RETURN;
  END IF;
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;
  IF caller_role NOT IN ('owner', 'admin') THEN
    RETURN;
  END IF;
  v_role := caller_role::app.user_role;
  BEGIN
    v_decision := p_decision::app.detector_review_decision;
  EXCEPTION
    WHEN invalid_text_representation THEN
      RETURN;
  END;

  SELECT df.document_id
  INTO v_document_id
  FROM app.detector_findings AS df
  INNER JOIN app.documents AS d ON d.id = df.document_id
  WHERE df.id = p_finding_id
    AND d.deleted_at IS NULL
    AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  LIMIT 1;
  IF v_document_id IS NULL THEN
    RETURN;
  END IF;

  SELECT r.id
  INTO v_existing
  FROM app.detector_finding_reviews AS r
  WHERE r.finding_id = p_finding_id
    AND r.idempotency_key = p_idempotency_key
    AND r.superseded_by IS NULL
  LIMIT 1;
  IF v_existing IS NOT NULL THEN
    RETURN QUERY
    SELECT v_existing, p_finding_id, v_decision::text, true;
    RETURN;
  END IF;

  v_audit := app.append_audit_event(
    'detector_finding_review',
    caller_user_id,
    v_role,
    'detector_finding',
    p_finding_id,
    caller_authorization_version,
    jsonb_build_object(
      'decision', v_decision::text,
      'idempotency_key', left(p_idempotency_key, 128)
    )
  );

  RETURN QUERY
  INSERT INTO app.detector_finding_reviews (
    finding_id,
    actor_user_id,
    actor_role,
    authorization_version,
    decision,
    reason,
    idempotency_key,
    audit_event_id
  )
  VALUES (
    p_finding_id,
    caller_user_id,
    v_role,
    caller_authorization_version,
    v_decision,
    left(btrim(p_reason), 500),
    p_idempotency_key,
    v_audit
  )
  RETURNING
    app.detector_finding_reviews.id,
    app.detector_finding_reviews.finding_id,
    app.detector_finding_reviews.decision::text,
    false;
EXCEPTION
  WHEN unique_violation THEN
    SELECT r.id
    INTO v_existing
    FROM app.detector_finding_reviews AS r
    WHERE r.finding_id = p_finding_id
      AND r.idempotency_key = p_idempotency_key
    LIMIT 1;
    IF v_existing IS NOT NULL THEN
      RETURN QUERY
      SELECT v_existing, p_finding_id, v_decision::text, true;
    END IF;
    RETURN;
END;
$fn$;

COMMENT ON FUNCTION app.review_detector_finding(uuid, text, bigint, uuid, text, text, text) IS
  'Owner/admin hash-bound detector review. Unauthorized callers see no row.';

REVOKE ALL ON FUNCTION app.review_detector_finding(uuid, text, bigint, uuid, text, text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.review_detector_finding(uuid, text, bigint, uuid, text, text, text)
  TO app_api;

CREATE OR REPLACE FUNCTION app.detector_reviews_cover_version(
  p_version_id uuid,
  p_content_hash text,
  p_scan_evidence_id uuid,
  p_attestation_policy_version text,
  p_detector_policy_version text,
  p_required_families text[]
)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_scan_hash text;
  v_scan_result app.scan_result;
  v_family text;
  v_ok boolean;
BEGIN
  IF p_required_families IS NULL OR cardinality(p_required_families) = 0 THEN
    RETURN true;
  END IF;
  SELECT se.object_hash, se.result
  INTO v_scan_hash, v_scan_result
  FROM app.document_scan_events AS se
  WHERE se.id = p_scan_evidence_id
    AND se.version_id = p_version_id
  LIMIT 1;
  IF v_scan_hash IS NULL
     OR v_scan_hash IS DISTINCT FROM p_content_hash
     OR v_scan_result IS DISTINCT FROM 'clean'::app.scan_result
  THEN
    RETURN false;
  END IF;
  FOREACH v_family IN ARRAY p_required_families
  LOOP
    SELECT EXISTS (
      SELECT 1
      FROM app.detector_finding_reviews AS r
      INNER JOIN app.detector_findings AS f ON f.id = r.finding_id
      WHERE f.version_id = p_version_id
        AND f.content_hash = p_content_hash
        AND f.attestation_policy_version = p_attestation_policy_version
        AND f.detector_policy_version = p_detector_policy_version
        AND f.detector_family = v_family
        AND r.decision = 'false_positive'
        AND r.superseded_by IS NULL
    )
    INTO v_ok;
    IF v_ok IS NOT TRUE THEN
      RETURN false;
    END IF;
  END LOOP;
  RETURN true;
END;
$fn$;

COMMENT ON FUNCTION app.detector_reviews_cover_version(uuid, text, uuid, text, text, text[]) IS
  'True when every required positive family has an active false-positive review for this hash/policy.';

GRANT EXECUTE ON FUNCTION app.detector_reviews_cover_version(uuid, text, uuid, text, text, text[])
  TO app_worker, app_api;

CREATE OR REPLACE FUNCTION app.version_governance_review_diagnostics(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_version_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN NULL;
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM app.document_versions AS dv
    INNER JOIN app.documents AS d ON d.id = dv.document_id
    WHERE dv.id = p_version_id
      AND d.deleted_at IS NULL
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ) THEN
    RETURN NULL;
  END IF;
  RETURN (
    SELECT jsonb_build_object(
      'finding_count', count(*)::int,
      'unresolved_family_count', count(*) FILTER (
        WHERE NOT EXISTS (
          SELECT 1
          FROM app.detector_finding_reviews AS r
          WHERE r.finding_id = f.id
            AND r.decision = 'false_positive'
            AND r.superseded_by IS NULL
        )
      )::int,
      'findings', coalesce(
        jsonb_agg(
          jsonb_build_object(
            'finding_id', f.id,
            'family', f.detector_family,
            'bounded_count', f.bounded_count,
            'scope', f.finding_scope,
            'detector_policy_version', f.detector_policy_version
          )
          ORDER BY f.created_at
        ),
        '[]'::jsonb
      )
    )
    FROM app.detector_findings AS f
    WHERE f.version_id = p_version_id
  );
END;
$fn$;

COMMENT ON FUNCTION app.version_governance_review_diagnostics(uuid, text, bigint, uuid) IS
  'Role-safe detector finding counts and finding IDs. No matched secrets.';

REVOKE ALL ON FUNCTION app.version_governance_review_diagnostics(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.version_governance_review_diagnostics(uuid, text, bigint, uuid)
  TO app_api;
