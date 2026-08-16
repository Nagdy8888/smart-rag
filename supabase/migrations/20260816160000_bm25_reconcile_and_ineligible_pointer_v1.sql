-- P2-4/P2-6: BM25 outbox reconcile claim, and Hybrid Ready pointer for
-- graph-ineligible versions. Expand-only: replace functions, add one RPC.
-- Does not alter app.switch_graph_document_version.

CREATE OR REPLACE FUNCTION app.finalize_hybrid_ready(
  p_version_id uuid,
  p_chunk_set_hash text,
  p_bm25_job_id uuid DEFAULT NULL
)
RETURNS app.document_versions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_row app.document_versions%ROWTYPE;
  doc app.documents%ROWTYPE;
BEGIN
  IF p_bm25_job_id IS NULL THEN
    RAISE EXCEPTION 'bm25 job required to finalize Hybrid Ready';
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.bm25_index_jobs AS j
    WHERE j.id = p_bm25_job_id
      AND j.version_id = p_version_id
      AND j.operation = 'upsert'
      AND j.status = 'processing'
  ) THEN
    RAISE EXCEPTION 'bm25 projection not verified for Hybrid Ready';
  END IF;

  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'version not found';
  END IF;

  IF version_row.chunk_set_hash IS DISTINCT FROM p_chunk_set_hash THEN
    RAISE EXCEPTION 'chunk_set_hash mismatch';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = version_row.document_id
  FOR UPDATE;

  UPDATE app.document_versions AS dv
  SET
    status = 'hybrid_ready'::app.document_status,
    hybrid_verified_at = timezone('utc', now()),
    bm25_verified_at = timezone('utc', now()),
    updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id
  RETURNING * INTO version_row;

  IF doc.graph_eligible
    AND doc.visibility = 'company_visible'::app.document_visibility
    AND doc.deleted_at IS NULL
    AND version_row.graph_eligible THEN
    PERFORM app.enqueue_graph_pending_handoff(p_version_id);
    SELECT * INTO version_row
    FROM app.document_versions AS dv
    WHERE dv.id = p_version_id;
  ELSE
    UPDATE app.document_versions AS dv
    SET status = 'graph_ineligible'::app.document_status,
        updated_at = timezone('utc', now())
    WHERE dv.id = p_version_id
      AND dv.status = 'hybrid_ready'::app.document_status
    RETURNING * INTO version_row;

    UPDATE app.document_versions AS dv
    SET is_current = false, updated_at = timezone('utc', now())
    WHERE dv.document_id = doc.id
      AND dv.is_current = true
      AND dv.id IS DISTINCT FROM p_version_id;

    UPDATE app.document_versions AS dv
    SET is_current = true, updated_at = timezone('utc', now())
    WHERE dv.id = p_version_id;

    UPDATE app.documents AS d
    SET current_version_id = p_version_id, updated_at = timezone('utc', now())
    WHERE d.id = doc.id;
  END IF;

  RETURN version_row;
END;
$fn$;

COMMENT ON FUNCTION app.finalize_hybrid_ready(uuid, text, uuid) IS
  'Marks Hybrid Ready only after a processing BM25 upsert job exists. Graph-ineligible versions become current here; graph-eligible replacements stay non-current for Phase 5 pointer CAS.';

CREATE OR REPLACE FUNCTION app.activate_graph_ineligible_version(
  p_version_id uuid
)
RETURNS app.documents
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  version_row app.document_versions%ROWTYPE;
  doc app.documents%ROWTYPE;
BEGIN
  SELECT * INTO version_row
  FROM app.document_versions AS dv
  WHERE dv.id = p_version_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'version not found';
  END IF;

  IF version_row.status NOT IN (
    'hybrid_ready'::app.document_status,
    'graph_ineligible'::app.document_status
  ) THEN
    RAISE EXCEPTION 'version must be hybrid_ready or graph_ineligible before activation';
  END IF;

  SELECT * INTO doc
  FROM app.documents AS d
  WHERE d.id = version_row.document_id
  FOR UPDATE;

  IF doc.graph_eligible OR version_row.graph_eligible THEN
    RAISE EXCEPTION 'graph-eligible versions require Phase 5 switch';
  END IF;

  UPDATE app.document_versions AS dv
  SET is_current = false, updated_at = timezone('utc', now())
  WHERE dv.document_id = doc.id AND dv.is_current = true;

  UPDATE app.document_versions AS dv
  SET is_current = true, updated_at = timezone('utc', now())
  WHERE dv.id = p_version_id;

  UPDATE app.documents AS d
  SET current_version_id = p_version_id, updated_at = timezone('utc', now())
  WHERE d.id = doc.id
  RETURNING * INTO doc;

  RETURN doc;
END;
$fn$;

COMMENT ON FUNCTION app.activate_graph_ineligible_version(uuid) IS
  'Phase 3 current-version pointer for graph-ineligible Hybrid Ready or Graph Ineligible versions. Graph-eligible rows fail closed.';

CREATE OR REPLACE FUNCTION app.claim_bm25_reconcile_job(
  p_owner text,
  p_lease_seconds integer
)
RETURNS SETOF app.bm25_index_jobs
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_now timestamptz := timezone('utc', now());
  v_job_id uuid;
  v_token text;
BEGIN
  PERFORM app._validate_job_owner(p_owner);
  PERFORM app._validate_job_lease_seconds(p_lease_seconds);

  SELECT j.id
  INTO v_job_id
  FROM app.bm25_index_jobs AS j
  WHERE j.status = 'processing'::app.job_status
    AND (
      j.lease_expires_at IS NULL
      OR j.lease_expires_at < v_now
    )
  ORDER BY
    CASE j.priority
      WHEN 'critical'::app.job_priority THEN 1
      WHEN 'high'::app.job_priority THEN 2
      WHEN 'normal'::app.job_priority THEN 3
      WHEN 'low'::app.job_priority THEN 4
    END,
    j.created_at ASC,
    j.estimated_size_bytes ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1;

  IF v_job_id IS NULL THEN
    RETURN;
  END IF;

  v_token := gen_random_uuid()::text;

  RETURN QUERY
  UPDATE app.bm25_index_jobs AS j
  SET
    status = 'processing'::app.job_status,
    lease_owner = p_owner,
    lease_token = v_token,
    lease_expires_at = v_now + make_interval(secs => p_lease_seconds),
    heartbeat_at = v_now,
    updated_at = v_now
  WHERE j.id = v_job_id
  RETURNING j.*;
END;
$fn$;

COMMENT ON FUNCTION app.claim_bm25_reconcile_job(text, integer) IS
  'Lease one stuck processing BM25 job whose lease is null or expired. Does not increment attempt_count. Live leases are not stolen.';

REVOKE ALL ON FUNCTION app.claim_bm25_reconcile_job(text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION app.claim_bm25_reconcile_job(text, integer) TO app_worker;
