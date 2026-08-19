-- PRD-C-010: ACL-gated ingestion status reads. app_api must not SELECT
-- diagnostic tables with USING (true). Status is a SECURITY DEFINER RPC that
-- applies app.caller_can_read_document and returns no row when unauthorized.

CREATE OR REPLACE FUNCTION app.sanitize_ingestion_last_error(
  p_error text,
  p_category text
)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF p_error IS NULL OR btrim(p_error) = '' THEN
    RETURN NULL;
  END IF;

  IF p_error ~* '(traceback|password=|secret|postgres(ql)?://|sk-[a-z0-9]|begin |exception)'
    OR position(E'\n' IN p_error) > 0
    OR char_length(p_error) > 240
  THEN
    IF p_category IS NULL OR btrim(p_category) = '' THEN
      RETURN 'ingestion_error';
    END IF;
    RETURN left(p_category, 64);
  END IF;

  RETURN left(p_error, 240);
END;
$fn$;

COMMENT ON FUNCTION app.sanitize_ingestion_last_error(text, text) IS
  'Strips stack traces and secret-like last_error text from ingestion job diagnostics.';

REVOKE ALL ON FUNCTION app.sanitize_ingestion_last_error(text, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.sanitize_ingestion_last_error(text, text) TO app_api;

CREATE OR REPLACE FUNCTION app.get_version_ingestion_status(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_version_id uuid
)
RETURNS TABLE (
  status_payload jsonb,
  recent_jobs jsonb
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  payload jsonb;
  jobs jsonb;
BEGIN
  IF p_version_id IS NULL THEN
    RETURN;
  END IF;

  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RETURN;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM app.document_versions AS dv
    INNER JOIN app.documents AS d ON d.id = dv.document_id
    WHERE dv.id = p_version_id
      AND d.deleted_at IS NULL
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  ) THEN
    RETURN;
  END IF;

  SELECT jsonb_build_object(
    'version_id', dv.id,
    'document_id', dv.document_id,
    'status', dv.status::text,
    'version_number', dv.version_number,
    'is_current', dv.is_current,
    'retrieval_eligible', dv.retrieval_eligible,
    'chunk_set_hash', dv.chunk_set_hash,
    'embedding_model', dv.embedding_model,
    'embedding_policy_hash', dv.embedding_policy_hash,
    'hybrid_verified_at', dv.hybrid_verified_at,
    'bm25_verified_at', dv.bm25_verified_at,
    'graph_handoff_at', dv.graph_handoff_at,
    'title', coalesce(d.title, ''),
    'visibility', d.visibility::text,
    'document_graph_eligible', d.graph_eligible,
    'visibility_generation', d.visibility_generation,
    'chunk_count', (
      SELECT count(*)
      FROM app.document_chunks AS dc
      WHERE dc.version_id = dv.id AND dc.deleted_at IS NULL
    ),
    'embedding_ledger_count', (
      SELECT count(*)
      FROM app.embedding_operation_ledger AS eol
      WHERE eol.version_id = dv.id
    ),
    'bm25_jobs', (
      SELECT jsonb_build_object(
        'pending', count(*) FILTER (WHERE status = 'pending'),
        'processing', count(*) FILTER (WHERE status = 'processing'),
        'failed', count(*) FILTER (WHERE status = 'failed'),
        'dead_letter', count(*) FILTER (WHERE status = 'dead_letter')
      )
      FROM app.bm25_index_jobs AS bj
      WHERE bj.version_id = dv.id
    ),
    'graph_handoff_jobs', (
      SELECT jsonb_build_object(
        'pending', count(*) FILTER (WHERE status = 'pending'),
        'processing', count(*) FILTER (WHERE status = 'processing')
      )
      FROM app.lightrag_index_jobs AS lj
      WHERE lj.version_id = dv.id
    ),
    'scan', (
      SELECT jsonb_build_object(
        'result', se.result::text,
        'evidence_id', se.id,
        'scanned_at', se.scanned_at,
        'age_seconds', extract(epoch FROM (timezone('utc', now()) - se.scanned_at)),
        'engine_version', se.scan_engine_version,
        'signature_version', se.signature_version,
        'object_hash', se.object_hash
      )
      FROM app.document_scan_events AS se
      WHERE se.version_id = dv.id
      ORDER BY se.scanned_at DESC
      LIMIT 1
    ),
    'review', (
      SELECT jsonb_build_object(
        'declared_category', ds.declared_category,
        'source_type', ds.source_type::text,
        'approval_status', (
          SELECT sar.status::text
          FROM app.source_approval_requests AS sar
          WHERE sar.source_id = ds.id
          ORDER BY sar.updated_at DESC
          LIMIT 1
        ),
        'attestation_policy_version', (
          SELECT j.payload_ref ->> 'attestation_policy_version'
          FROM app.ingestion_jobs AS j
          WHERE j.version_id = dv.id
          ORDER BY j.created_at
          LIMIT 1
        )
      )
      FROM app.document_sources AS ds
      WHERE ds.version_id = dv.id
      ORDER BY ds.created_at
      LIMIT 1
    ),
    'ocr', jsonb_build_object(
      'page_count', coalesce((
        SELECT count(DISTINCT dc.page_number)
        FROM app.document_chunks AS dc
        WHERE dc.version_id = dv.id
          AND dc.deleted_at IS NULL
          AND dc.page_number IS NOT NULL
      ), 0),
      'ocr_pages', coalesce((
        SELECT count(DISTINCT dc.page_number)
        FROM app.document_chunks AS dc
        WHERE dc.version_id = dv.id
          AND dc.deleted_at IS NULL
          AND dc.page_number IS NOT NULL
          AND coalesce((dc.provenance ->> 'ocr')::boolean, false)
      ), 0)
    ),
    'chunks_tables', jsonb_build_object(
      'chunk_count', (
        SELECT count(*)
        FROM app.document_chunks AS dc
        WHERE dc.version_id = dv.id AND dc.deleted_at IS NULL
      ),
      'table_count', (
        SELECT count(*)
        FROM app.document_tables AS dt
        WHERE dt.version_id = dv.id
      )
    ),
    'embedding', jsonb_build_object(
      'ledger_count', (
        SELECT count(*)
        FROM app.embedding_operation_ledger AS eol
        WHERE eol.version_id = dv.id
      ),
      'completed_count', (
        SELECT count(*)
        FROM app.embedding_operation_ledger AS eol
        WHERE eol.version_id = dv.id AND eol.status = 'completed'
      ),
      'failed_count', (
        SELECT count(*)
        FROM app.embedding_operation_ledger AS eol
        WHERE eol.version_id = dv.id AND eol.status = 'failed'
      ),
      'model', dv.embedding_model,
      'policy_hash', dv.embedding_policy_hash
    ),
    'bm25', jsonb_build_object(
      'active_index_version', (
        SELECT biv.version_number
        FROM app.bm25_index_versions AS biv
        WHERE biv.is_active = true
        ORDER BY biv.version_number DESC
        LIMIT 1
      ),
      'index_schema_version', (
        SELECT biv.index_schema_version
        FROM app.bm25_index_versions AS biv
        WHERE biv.is_active = true
        ORDER BY biv.version_number DESC
        LIMIT 1
      ),
      'lag_seconds', CASE
        WHEN dv.hybrid_verified_at IS NOT NULL
          AND dv.bm25_verified_at IS NULL THEN
          extract(epoch FROM (timezone('utc', now()) - dv.hybrid_verified_at))
        WHEN EXISTS (
          SELECT 1
          FROM app.bm25_index_jobs AS bj
          WHERE bj.version_id = dv.id
            AND bj.status IN ('pending', 'processing')
        ) THEN
          extract(
            epoch FROM (
              timezone('utc', now()) - (
                SELECT min(bj.created_at)
                FROM app.bm25_index_jobs AS bj
                WHERE bj.version_id = dv.id
                  AND bj.status IN ('pending', 'processing')
              )
            )
          )
        ELSE NULL
      END,
      'pending', (
        SELECT count(*)
        FROM app.bm25_index_jobs AS bj
        WHERE bj.version_id = dv.id AND bj.status = 'pending'
      ),
      'processing', (
        SELECT count(*)
        FROM app.bm25_index_jobs AS bj
        WHERE bj.version_id = dv.id AND bj.status = 'processing'
      ),
      'failed', (
        SELECT count(*)
        FROM app.bm25_index_jobs AS bj
        WHERE bj.version_id = dv.id AND bj.status = 'failed'
      ),
      'dead_letter', (
        SELECT count(*)
        FROM app.bm25_index_jobs AS bj
        WHERE bj.version_id = dv.id AND bj.status = 'dead_letter'
      ),
      'retry_attempts', (
        SELECT coalesce(sum(bj.attempt_count), 0)
        FROM app.bm25_index_jobs AS bj
        WHERE bj.version_id = dv.id
      ),
      'verified_at', dv.bm25_verified_at
    ),
    'queue_age', (
      SELECT jsonb_build_object(
        'oldest_pending_job_age_seconds', extract(
          epoch FROM (timezone('utc', now()) - j.created_at)
        ),
        'oldest_pending_job_kind', j.job_kind
      )
      FROM app.ingestion_jobs AS j
      WHERE j.version_id = dv.id AND j.status = 'pending'
      ORDER BY j.created_at
      LIMIT 1
    ),
    'graph_handoff', (
      SELECT jsonb_build_object(
        'pending', count(*) FILTER (WHERE status = 'pending'),
        'processing', count(*) FILTER (WHERE status = 'processing'),
        'completed', count(*) FILTER (WHERE status = 'completed'),
        'failed', count(*) FILTER (WHERE status = 'failed'),
        'dead_letter', count(*) FILTER (WHERE status = 'dead_letter')
      )
      FROM app.lightrag_index_jobs AS lj
      WHERE lj.version_id = dv.id
    )
  )
  INTO payload
  FROM app.document_versions AS dv
  INNER JOIN app.documents AS d ON d.id = dv.document_id
  WHERE dv.id = p_version_id;

  SELECT coalesce(
    jsonb_agg(job_row.job ORDER BY job_row.created_at DESC),
    '[]'::jsonb
  )
  INTO jobs
  FROM (
    SELECT
      j.created_at,
      jsonb_build_object(
        'id', j.id,
        'job_kind', j.job_kind,
        'status', j.status::text,
        'priority', j.priority::text,
        'attempt_count', j.attempt_count,
        'max_attempts', j.max_attempts,
        'error_category', j.error_category::text,
        'last_error', app.sanitize_ingestion_last_error(
          j.last_error,
          j.error_category::text
        ),
        'created_at', j.created_at,
        'updated_at', j.updated_at
      ) AS job
    FROM app.ingestion_jobs AS j
    WHERE j.document_id = (payload ->> 'document_id')::uuid
    ORDER BY j.created_at DESC
    LIMIT 20
  ) AS job_row;

  status_payload := payload;
  recent_jobs := jobs;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.get_version_ingestion_status(uuid, text, bigint, uuid) IS
  'ACL-filtered ingestion status. Missing or unauthorized versions return no row (HTTP 404).';

REVOKE ALL ON FUNCTION app.get_version_ingestion_status(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.get_version_ingestion_status(uuid, text, bigint, uuid)
  TO app_api;

-- Hybrid retrieval and table resolve are SECURITY INVOKER as app_api, so
-- versions/chunks/tables keep USING (true). HTTP status no longer SELECTs
-- those tables; it uses app.get_version_ingestion_status instead.
DROP POLICY IF EXISTS document_versions_api_status_read ON app.document_versions;
CREATE POLICY document_versions_api_status_read
  ON app.document_versions
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_chunks_api_status_read ON app.document_chunks;
CREATE POLICY document_chunks_api_status_read
  ON app.document_chunks
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_tables_api_status_read ON app.document_tables;
CREATE POLICY document_tables_api_status_read
  ON app.document_tables
  FOR SELECT
  TO app_api
  USING (true);

DROP POLICY IF EXISTS document_sources_api_status_read ON app.document_sources;
CREATE POLICY document_sources_api_status_read
  ON app.document_sources
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS document_scan_events_api_status_read ON app.document_scan_events;
CREATE POLICY document_scan_events_api_status_read
  ON app.document_scan_events
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS ingestion_jobs_api_status_read ON app.ingestion_jobs;
CREATE POLICY ingestion_jobs_api_status_read
  ON app.ingestion_jobs
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS embedding_ledger_api_status_read ON app.embedding_operation_ledger;
CREATE POLICY embedding_ledger_api_status_read
  ON app.embedding_operation_ledger
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS bm25_jobs_api_status_read ON app.bm25_index_jobs;
CREATE POLICY bm25_jobs_api_status_read
  ON app.bm25_index_jobs
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS bm25_versions_api_status_read ON app.bm25_index_versions;
CREATE POLICY bm25_versions_api_status_read
  ON app.bm25_index_versions
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS lightrag_jobs_api_status_read ON app.lightrag_index_jobs;
CREATE POLICY lightrag_jobs_api_status_read
  ON app.lightrag_index_jobs
  FOR SELECT
  TO app_api
  USING (false);

DROP POLICY IF EXISTS source_approvals_api_status_read ON app.source_approval_requests;
CREATE POLICY source_approvals_api_status_read
  ON app.source_approval_requests
  FOR SELECT
  TO app_api
  USING (false);

-- Diagnostic tables are not read by INVOKER retrieval. FORCE RLS so a
-- table-owner DSN cannot skip the USING (false) app_api policies.
ALTER TABLE app.document_sources FORCE ROW LEVEL SECURITY;
ALTER TABLE app.document_scan_events FORCE ROW LEVEL SECURITY;
ALTER TABLE app.ingestion_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.embedding_operation_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE app.bm25_index_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.bm25_index_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE app.lightrag_index_jobs FORCE ROW LEVEL SECURITY;
ALTER TABLE app.source_approval_requests FORCE ROW LEVEL SECURITY;
