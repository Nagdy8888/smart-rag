-- Phase 3 gap: app_worker had INSERT grants on document_scan_events but no RLS
-- policy. ENABLE ROW LEVEL SECURITY default-denies inserts after SET ROLE
-- app_worker, so scan_and_govern raised ScanEventRepositoryError and left the
-- ingestion job leased until expiry.

DROP POLICY IF EXISTS document_scan_events_worker_insert ON app.document_scan_events;
CREATE POLICY document_scan_events_worker_insert
  ON app.document_scan_events
  FOR INSERT
  TO app_worker
  WITH CHECK (true);

DROP POLICY IF EXISTS document_scan_events_worker_select ON app.document_scan_events;
CREATE POLICY document_scan_events_worker_select
  ON app.document_scan_events
  FOR SELECT
  TO app_worker
  USING (true);

COMMENT ON POLICY document_scan_events_worker_insert ON app.document_scan_events IS
  'Worker append-only scan evidence. UPDATE/DELETE stay blocked by triggers.';

COMMENT ON POLICY document_scan_events_worker_select ON app.document_scan_events IS
  'Worker reads current clean-scan evidence before promotion.';
