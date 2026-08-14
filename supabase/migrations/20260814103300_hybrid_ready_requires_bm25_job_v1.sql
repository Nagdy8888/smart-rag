-- Phase 3 gap close-out Run 4: Hybrid Ready requires a processing BM25 upsert job.

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
  ELSE
    UPDATE app.document_versions AS dv
    SET status = 'graph_ineligible'::app.document_status,
        updated_at = timezone('utc', now())
    WHERE dv.id = p_version_id
      AND dv.status = 'hybrid_ready'::app.document_status
    RETURNING * INTO version_row;
  END IF;

  RETURN version_row;
END;
$fn$;

COMMENT ON FUNCTION app.finalize_hybrid_ready(uuid, text, uuid) IS
  'Marks Hybrid Ready only after a processing BM25 upsert job exists for the version.';
