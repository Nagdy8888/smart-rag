-- Phase 2 Packet 2: LLM usage, budget reservations, upload quota reservations.

CREATE TABLE app.llm_usage (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  run_id uuid REFERENCES app.runs (id) ON DELETE SET NULL,
  model_id text NOT NULL,
  prompt_tokens integer NOT NULL DEFAULT 0,
  completion_tokens integer NOT NULL DEFAULT 0,
  total_tokens integer NOT NULL DEFAULT 0,
  cost_usd numeric(12, 6) NOT NULL DEFAULT 0,
  usage_kind text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE app.budget_reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  run_id uuid REFERENCES app.runs (id) ON DELETE SET NULL,
  reservation_kind text NOT NULL,
  amount_usd numeric(12, 6) NOT NULL,
  status app.budget_reservation_status NOT NULL DEFAULT 'reserved',
  expires_at timestamptz NOT NULL,
  committed_at timestamptz,
  released_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT budget_reservations_amount_positive CHECK (amount_usd > 0)
);

CREATE TABLE app.upload_quota_reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users (id) ON DELETE CASCADE,
  reserved_bytes bigint NOT NULL,
  status app.budget_reservation_status NOT NULL DEFAULT 'reserved',
  expires_at timestamptz NOT NULL,
  storage_bucket text,
  storage_path text,
  committed_at timestamptz,
  released_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT upload_quota_reservations_bytes_positive CHECK (reserved_bytes > 0)
);

COMMENT ON TABLE app.budget_reservations IS
  'Durable reserve-once LLM budget holds. Valkey is never authoritative for spend.';

COMMENT ON COLUMN app.company_settings.visibility_generation IS
  'Monotonic generation bumped with authorization/visibility changes for cache invalidation.';

COMMENT ON COLUMN app.documents.visibility_generation IS
  'Per-document generation for BM25/cache invalidation on ACL or deletion changes.';

CREATE TRIGGER budget_reservations_touch_updated_at
  BEFORE UPDATE ON app.budget_reservations
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER upload_quota_reservations_touch_updated_at
  BEFORE UPDATE ON app.upload_quota_reservations
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
