-- Phase 2 Packet 2: identity profile, singleton company settings, invitations, degraded limits.

CREATE TABLE app.profiles (
  user_id uuid PRIMARY KEY REFERENCES auth.users (id) ON DELETE CASCADE,
  role app.user_role NOT NULL DEFAULT 'member',
  display_name text,
  upload_enabled boolean NOT NULL DEFAULT false,
  mfa_enrolled boolean NOT NULL DEFAULT false,
  disabled_at timestamptz,
  session_revoked_at timestamptz,
  monthly_llm_budget_usd numeric(12, 4),
  daily_ingestion_budget_usd numeric(12, 4),
  upload_quota_bytes bigint,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE app.profiles IS
  'Authoritative membership role and per-user limits. Packet 3 RLS enforces reads/writes.';

CREATE TABLE app.company_settings (
  id uuid PRIMARY KEY DEFAULT '00000000-0000-0000-0000-000000000001'::uuid,
  company_name text,
  authorization_version bigint NOT NULL DEFAULT 1,
  default_document_visibility app.document_visibility NOT NULL DEFAULT 'company_visible',
  visibility_generation bigint NOT NULL DEFAULT 1,
  monthly_llm_budget_usd numeric(12, 4),
  daily_ingestion_budget_usd numeric(12, 4),
  upload_quota_bytes bigint,
  quarantine_byte_cap bigint,
  timezone text NOT NULL DEFAULT 'UTC',
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT company_settings_singleton CHECK (
    id = '00000000-0000-0000-0000-000000000001'::uuid
  )
);

COMMENT ON TABLE app.company_settings IS
  'Singleton company policy including monotonic authorization_version and visibility_generation.';

INSERT INTO app.company_settings (id)
VALUES ('00000000-0000-0000-0000-000000000001'::uuid)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE app.allowed_email_domains (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  domain text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT allowed_email_domains_domain_lower CHECK (domain = lower(domain)),
  CONSTRAINT allowed_email_domains_domain_nonempty CHECK (btrim(domain) <> '')
);

CREATE UNIQUE INDEX allowed_email_domains_domain_uq
  ON app.allowed_email_domains (domain);

CREATE TABLE app.team_invitations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text NOT NULL,
  invited_by uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  role app.user_role NOT NULL DEFAULT 'member',
  token_hash text NOT NULL,
  expires_at timestamptz NOT NULL,
  accepted_at timestamptz,
  revoked_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT team_invitations_email_lower CHECK (email = lower(email))
);

CREATE UNIQUE INDEX team_invitations_token_hash_uq
  ON app.team_invitations (token_hash);

CREATE TABLE private.auth_rate_limit_buckets (
  bucket_key text NOT NULL,
  window_start timestamptz NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  PRIMARY KEY (bucket_key, window_start)
);

COMMENT ON TABLE private.auth_rate_limit_buckets IS
  'Postgres degraded path when Valkey limits are unavailable. FastAPI-owned writes only.';

CREATE TRIGGER profiles_touch_updated_at
  BEFORE UPDATE ON app.profiles
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER company_settings_touch_updated_at
  BEFORE UPDATE ON app.company_settings
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER team_invitations_touch_updated_at
  BEFORE UPDATE ON app.team_invitations
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
