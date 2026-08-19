-- PRD-H-031: Owner/admin document delete wraps exclude_version_from_retrieval.
-- Tombstones the document, drops current_version_id, and attaches Storage
-- coordinates onto the existing BM25 delete jobs.

CREATE OR REPLACE FUNCTION app.delete_visible_document(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc app.documents%ROWTYPE;
  version_row app.document_versions%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;

  SELECT *
  INTO doc
  FROM app.documents AS d
  WHERE d.id = p_document_id
  FOR UPDATE;

  IF NOT FOUND OR doc.deleted_at IS NOT NULL THEN
    RETURN NULL;
  END IF;

  IF NOT app.caller_can_read_document(caller_user_id, caller_role, doc.id) THEN
    RETURN NULL;
  END IF;

  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'documents:forbidden';
  END IF;

  FOR version_row IN
    SELECT *
    FROM app.document_versions AS dv
    WHERE dv.document_id = doc.id
    ORDER BY dv.version_number
    FOR UPDATE
  LOOP
    IF version_row.deleted_at IS NULL THEN
      PERFORM app.exclude_version_from_retrieval(
        version_row.id,
        'http_document_delete'
      );
    END IF;

    UPDATE app.bm25_index_jobs
    SET payload_ref = coalesce(payload_ref, '{}'::jsonb) || jsonb_build_object(
      'storage_bucket', version_row.storage_bucket,
      'storage_path', version_row.storage_path,
      'storage_cleanup', true
    )
    WHERE version_id = version_row.id
      AND operation = 'delete'::app.bm25_job_operation;
  END LOOP;

  UPDATE app.documents
  SET
    deleted_at = coalesce(deleted_at, timezone('utc', now())),
    current_version_id = NULL,
    graph_eligible = false,
    updated_at = timezone('utc', now())
  WHERE id = doc.id;

  PERFORM app.append_audit_event(
    'document.deleted',
    caller_user_id,
    caller_role::app.user_role,
    'document',
    doc.id,
    app.current_authorization_version(),
    jsonb_build_object('reason', 'http_document_delete')
  );

  RETURN doc.id;
END;
$fn$;

COMMENT ON FUNCTION app.delete_visible_document(uuid, text, bigint, uuid) IS
  'Owner/admin document tombstone. Wraps exclude_version_from_retrieval; unauthorized ids return NULL.';

REVOKE ALL ON FUNCTION app.delete_visible_document(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.delete_visible_document(uuid, text, bigint, uuid)
  TO app_api;
