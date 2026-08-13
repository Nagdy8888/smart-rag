-- Phase 3 Packet 4: crawl runs, immutable web snapshots, fetch provenance.

ALTER TABLE app.source_approval_requests
  ADD COLUMN IF NOT EXISTS policy_version text,
  ADD COLUMN IF NOT EXISTS expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS max_depth integer NOT NULL DEFAULT 2,
  ADD COLUMN IF NOT EXISTS max_pages integer NOT NULL DEFAULT 50;

DO $approval_constraints$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_approval_requests_max_depth_positive'
  ) THEN
    ALTER TABLE app.source_approval_requests
      ADD CONSTRAINT source_approval_requests_max_depth_positive
      CHECK (max_depth > 0 AND max_depth <= 5);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'source_approval_requests_max_pages_positive'
  ) THEN
    ALTER TABLE app.source_approval_requests
      ADD CONSTRAINT source_approval_requests_max_pages_positive
      CHECK (max_pages > 0 AND max_pages <= 200);
  END IF;
END;
$approval_constraints$;

CREATE TABLE IF NOT EXISTS app.web_crawl_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id uuid NOT NULL REFERENCES app.document_sources (id) ON DELETE CASCADE,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE SET NULL,
  crawl_version integer NOT NULL,
  policy_version text NOT NULL,
  start_url text NOT NULL,
  status text NOT NULL DEFAULT 'running',
  pages_fetched integer NOT NULL DEFAULT 0,
  wire_bytes_total bigint NOT NULL DEFAULT 0,
  decoded_bytes_total bigint NOT NULL DEFAULT 0,
  failure_reason text,
  started_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  completed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT web_crawl_runs_version_positive CHECK (crawl_version > 0),
  CONSTRAINT web_crawl_runs_status_check CHECK (
    status IN ('running', 'completed', 'failed')
  ),
  CONSTRAINT web_crawl_runs_source_version_uq UNIQUE (source_id, crawl_version)
);

COMMENT ON TABLE app.web_crawl_runs IS
  'One bounded website crawl execution for an approved source.';

CREATE TABLE IF NOT EXISTS app.web_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  crawl_run_id uuid NOT NULL REFERENCES app.web_crawl_runs (id) ON DELETE CASCADE,
  source_id uuid NOT NULL REFERENCES app.document_sources (id) ON DELETE CASCADE,
  canonical_url text NOT NULL,
  title text,
  content_type text,
  content_hash text NOT NULL,
  storage_bucket text NOT NULL,
  storage_path text NOT NULL,
  wire_bytes bigint NOT NULL DEFAULT 0,
  decoded_bytes bigint NOT NULL DEFAULT 0,
  redirect_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
  peer_ip text,
  pinned_ips jsonb NOT NULL DEFAULT '[]'::jsonb,
  fetched_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT web_snapshots_hash_present CHECK (content_hash <> ''),
  CONSTRAINT web_snapshots_storage_path_uq UNIQUE (storage_bucket, storage_path)
);

COMMENT ON TABLE app.web_snapshots IS
  'Immutable HTML/text snapshots stored in web-snapshots bucket.';

CREATE TABLE IF NOT EXISTS app.crawl_fetch_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  crawl_run_id uuid REFERENCES app.web_crawl_runs (id) ON DELETE CASCADE,
  requested_url text NOT NULL,
  final_url text NOT NULL,
  status_code integer,
  decision text NOT NULL,
  reason text NOT NULL,
  peer_ip text,
  pinned_ips jsonb NOT NULL DEFAULT '[]'::jsonb,
  redirect_hop integer NOT NULL DEFAULT 0,
  wire_bytes bigint NOT NULL DEFAULT 0,
  decoded_bytes bigint NOT NULL DEFAULT 0,
  content_type text,
  robots jsonb,
  policy_version text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

COMMENT ON TABLE app.crawl_fetch_events IS
  'Append-only crawl fetch provenance including DNS/peer decisions.';

CREATE INDEX IF NOT EXISTS web_crawl_runs_source_idx
  ON app.web_crawl_runs (source_id);

CREATE INDEX IF NOT EXISTS web_snapshots_run_idx
  ON app.web_snapshots (crawl_run_id);

CREATE INDEX IF NOT EXISTS crawl_fetch_events_run_idx
  ON app.crawl_fetch_events (crawl_run_id);

CREATE TRIGGER web_crawl_runs_touch_updated_at
  BEFORE UPDATE ON app.web_crawl_runs
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

ALTER TABLE app.web_crawl_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.web_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.crawl_fetch_events ENABLE ROW LEVEL SECURITY;

ALTER TABLE app.web_crawl_runs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.web_snapshots FORCE ROW LEVEL SECURITY;
ALTER TABLE app.crawl_fetch_events FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS web_crawl_runs_worker_all ON app.web_crawl_runs;
CREATE POLICY web_crawl_runs_worker_all
  ON app.web_crawl_runs
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS web_snapshots_worker_all ON app.web_snapshots;
CREATE POLICY web_snapshots_worker_all
  ON app.web_snapshots
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS crawl_fetch_events_worker_insert ON app.crawl_fetch_events;
CREATE POLICY crawl_fetch_events_worker_insert
  ON app.crawl_fetch_events
  FOR INSERT
  TO app_worker
  WITH CHECK (true);

DROP POLICY IF EXISTS crawl_fetch_events_worker_select ON app.crawl_fetch_events;
CREATE POLICY crawl_fetch_events_worker_select
  ON app.crawl_fetch_events
  FOR SELECT
  TO app_worker
  USING (true);

DROP POLICY IF EXISTS web_crawl_runs_api_select ON app.web_crawl_runs;
CREATE POLICY web_crawl_runs_api_select
  ON app.web_crawl_runs
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS web_snapshots_api_select ON app.web_snapshots;
CREATE POLICY web_snapshots_api_select
  ON app.web_snapshots
  FOR SELECT
  TO app_api
  USING (true);

GRANT SELECT, INSERT, UPDATE ON app.web_crawl_runs TO app_worker;
GRANT SELECT, INSERT ON app.web_snapshots TO app_worker;
GRANT SELECT, INSERT ON app.crawl_fetch_events TO app_worker;
GRANT SELECT ON app.web_crawl_runs TO app_api;
GRANT SELECT ON app.web_snapshots TO app_api;

CREATE OR REPLACE FUNCTION app.load_active_crawl_approval(p_source_id uuid)
RETURNS TABLE (
  approval_id uuid,
  source_id uuid,
  start_url text,
  approved_domain text,
  policy_version text,
  max_depth integer,
  max_pages integer,
  requester_user_id uuid,
  reviewer_user_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RETURN QUERY
  SELECT
    sar.id,
    sar.source_id,
    sar.start_url,
    sar.domain,
    coalesce(sar.policy_version, 'crawl_v1'),
    sar.max_depth,
    sar.max_pages,
    sar.requested_by,
    sar.reviewed_by
  FROM app.source_approval_requests AS sar
  INNER JOIN app.document_sources AS ds ON ds.id = sar.source_id
  WHERE sar.source_id = p_source_id
    AND sar.status = 'approved'::app.approval_status
    AND sar.start_url IS NOT NULL
    AND sar.domain IS NOT NULL
    AND (sar.expires_at IS NULL OR sar.expires_at > timezone('utc', now()))
  ORDER BY sar.updated_at DESC
  LIMIT 1;
END;
$fn$;

COMMENT ON FUNCTION app.load_active_crawl_approval(uuid) IS
  'Return the latest non-expired approved crawl scope for a source.';

REVOKE ALL ON FUNCTION app.load_active_crawl_approval(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.load_active_crawl_approval(uuid) TO app_worker;
