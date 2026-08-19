-- PRD-M-024: owner/admin crawl enqueue ignores client content_class and
-- graph_eligible. Server policy is real_company + graph_eligible=false.
-- source_approval_requests remains the approval record in this transaction.

CREATE OR REPLACE FUNCTION app.enqueue_approved_website_crawl(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  start_url text,
  approved_domain text,
  document_title text,
  idempotency_key text,
  max_depth integer DEFAULT 2,
  max_pages integer DEFAULT 50,
  content_class text DEFAULT 'synthetic',
  graph_eligible boolean DEFAULT false,
  attestation_policy_version text DEFAULT NULL
)
RETURNS TABLE (
  document_id uuid,
  version_id uuid,
  source_id uuid,
  approval_id uuid,
  job_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  existing app.ingestion_jobs%ROWTYPE;
  new_document_id uuid;
  new_version_id uuid;
  new_source_id uuid;
  new_approval_id uuid;
  new_job_id uuid;
  safe_title text;
  visibility_value app.document_visibility;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  SELECT * INTO profile_row
  FROM app.profiles AS p
  WHERE p.user_id = caller_user_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'profile missing';
  END IF;

  IF profile_row.role NOT IN ('owner'::app.user_role, 'admin'::app.user_role) THEN
    RAISE EXCEPTION 'forbidden';
  END IF;

  IF start_url IS NULL OR btrim(start_url) = '' THEN
    RAISE EXCEPTION 'start_url required';
  END IF;

  IF approved_domain IS NULL OR btrim(approved_domain) = '' THEN
    RAISE EXCEPTION 'approved_domain required';
  END IF;

  IF idempotency_key IS NULL OR btrim(idempotency_key) = '' THEN
    RAISE EXCEPTION 'idempotency_key required';
  END IF;

  IF max_depth IS NULL OR max_depth < 1 OR max_depth > 5 THEN
    RAISE EXCEPTION 'max_depth out of bounds';
  END IF;

  IF max_pages IS NULL OR max_pages < 1 OR max_pages > 200 THEN
    RAISE EXCEPTION 'max_pages out of bounds';
  END IF;

  content_class := 'real_company';
  graph_eligible := false;

  SELECT * INTO existing
  FROM app.ingestion_jobs AS j
  WHERE j.idempotency_key = enqueue_approved_website_crawl.idempotency_key;

  IF FOUND THEN
    document_id := existing.document_id;
    version_id := existing.version_id;
    job_id := existing.id;
    SELECT ds.id INTO source_id
    FROM app.document_sources AS ds
    WHERE ds.document_id = existing.document_id
      AND ds.source_type = 'website_crawl'::app.source_type
    ORDER BY ds.created_at
    LIMIT 1;
    SELECT sar.id INTO approval_id
    FROM app.source_approval_requests AS sar
    WHERE sar.source_id = source_id
    ORDER BY sar.created_at DESC
    LIMIT 1;
    RETURN NEXT;
    RETURN;
  END IF;

  safe_title := coalesce(nullif(btrim(document_title), ''), start_url);
  visibility_value := 'company_visible'::app.document_visibility;

  INSERT INTO app.documents (title, visibility, created_by, graph_eligible)
  VALUES (safe_title, visibility_value, caller_user_id, false)
  RETURNING id INTO new_document_id;

  INSERT INTO app.document_versions (
    document_id,
    version_number,
    status,
    created_by,
    graph_eligible
  )
  VALUES (
    new_document_id,
    1,
    'uploaded'::app.document_status,
    caller_user_id,
    false
  )
  RETURNING id INTO new_version_id;

  UPDATE app.documents
  SET current_version_id = new_version_id, updated_at = timezone('utc', now())
  WHERE id = new_document_id;

  INSERT INTO app.document_sources (
    document_id,
    version_id,
    source_type,
    source_uri,
    approval_required,
    declared_category
  )
  VALUES (
    new_document_id,
    new_version_id,
    'website_crawl'::app.source_type,
    start_url,
    true,
    'website'
  )
  RETURNING id INTO new_source_id;

  INSERT INTO app.source_approval_requests (
    source_id,
    requested_by,
    reviewed_by,
    status,
    domain,
    start_url,
    policy_version,
    max_depth,
    max_pages
  )
  VALUES (
    new_source_id,
    caller_user_id,
    caller_user_id,
    'approved'::app.approval_status,
    lower(approved_domain),
    start_url,
    'crawl_v1',
    max_depth,
    max_pages
  )
  RETURNING id INTO new_approval_id;

  INSERT INTO app.ingestion_jobs (
    document_id,
    version_id,
    job_kind,
    idempotency_key,
    payload_ref
  )
  VALUES (
    new_document_id,
    new_version_id,
    'website_crawl',
    enqueue_approved_website_crawl.idempotency_key,
    jsonb_build_object(
      'operation_key', enqueue_approved_website_crawl.idempotency_key,
      'source_id', new_source_id,
      'approval_id', new_approval_id,
      'start_url', start_url,
      'approved_domain', lower(approved_domain),
      'content_class', 'real_company',
      'graph_eligible', false,
      'attestation_policy_version', attestation_policy_version
    )
  )
  RETURNING id INTO new_job_id;

  document_id := new_document_id;
  version_id := new_version_id;
  source_id := new_source_id;
  approval_id := new_approval_id;
  job_id := new_job_id;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.enqueue_approved_website_crawl(
  uuid, text, bigint, text, text, text, text, integer, integer, text, boolean, text
) IS
  'Owner/admin crawl enqueue. Ignores client content_class/graph_eligible; '
  'server policy is real_company and graph_eligible=false.';
