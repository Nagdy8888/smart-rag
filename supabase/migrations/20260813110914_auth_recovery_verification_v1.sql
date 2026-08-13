-- Phase 2 Packet 4 remediation: durable out-of-band MFA recovery proof.
-- This migration sorts before the original Packet 4 request-table migration,
-- so request linkage is enforced by a deferred constraint trigger at runtime.

CREATE TABLE app.mfa_recovery_verifications (
  recovery_request_id uuid PRIMARY KEY,
  subject_user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  verified_by uuid NOT NULL REFERENCES auth.users (id) ON DELETE RESTRICT,
  verification_method text NOT NULL,
  verification_reference text NOT NULL,
  verified_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  expires_at timestamptz NOT NULL DEFAULT (
    timezone('utc', now()) + interval '30 minutes'
  ),
  CONSTRAINT mfa_recovery_verification_method_bounded CHECK (
    char_length(btrim(verification_method)) BETWEEN 3 AND 64
  ),
  CONSTRAINT mfa_recovery_verification_reference_bounded CHECK (
    char_length(btrim(verification_reference)) BETWEEN 3 AND 128
  ),
  CONSTRAINT mfa_recovery_verification_distinct_actor CHECK (
    verified_by IS DISTINCT FROM subject_user_id
  ),
  CONSTRAINT mfa_recovery_verification_expiry_after_verification CHECK (
    expires_at > verified_at
  )
);

COMMENT ON TABLE app.mfa_recovery_verifications IS
  'Append-only out-of-band identity re-verification metadata; stores references, never evidence secrets.';
COMMENT ON COLUMN app.mfa_recovery_verifications.verification_method IS
  'Bounded method label such as manager_video_call; never a secret or transcript.';
COMMENT ON COLUMN app.mfa_recovery_verifications.verification_reference IS
  'Bounded external case/ticket identifier; never raw identity evidence.';

CREATE OR REPLACE FUNCTION app.block_mfa_recovery_verification_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $fn$
BEGIN
  RAISE EXCEPTION 'mfa_recovery_verifications is append-only';
END;
$fn$;

CREATE TRIGGER mfa_recovery_verifications_block_update
  BEFORE UPDATE OR DELETE ON app.mfa_recovery_verifications
  FOR EACH ROW
  EXECUTE FUNCTION app.block_mfa_recovery_verification_mutation();

CREATE OR REPLACE FUNCTION app.assert_mfa_recovery_request_link()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog
AS $fn$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM app.mfa_recovery_requests AS request
    WHERE request.id = NEW.recovery_request_id
      AND request.subject_user_id = NEW.subject_user_id
  ) THEN
    RAISE EXCEPTION 'MFA recovery verification request link is invalid';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE CONSTRAINT TRIGGER mfa_recovery_verifications_request_link
  AFTER INSERT ON app.mfa_recovery_verifications
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW
  EXECUTE FUNCTION app.assert_mfa_recovery_request_link();

ALTER TABLE app.mfa_recovery_verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.mfa_recovery_verifications FORCE ROW LEVEL SECURITY;

REVOKE ALL ON app.mfa_recovery_verifications FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.block_mfa_recovery_verification_mutation() FROM PUBLIC;
REVOKE ALL ON FUNCTION app.assert_mfa_recovery_request_link() FROM PUBLIC;
