-- The cited current version is enough to render one page.
-- A path suffix or an exact PDF media type is not required.

CREATE OR REPLACE FUNCTION app.get_citation_page_object_v1(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_run_id uuid,
  p_citation_id uuid
)
RETURNS TABLE (
  storage_bucket text,
  storage_path text,
  pdf_page_number integer
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  detail record;
BEGIN
  SELECT *
  INTO detail
  FROM app.get_run_citation_detail_v1(
    caller_user_id,
    caller_role,
    caller_authorization_version,
    p_run_id,
    p_citation_id
  ) AS cited;

  IF detail.source_unavailable
    OR detail.source_kind IS DISTINCT FROM 'company_document'
    OR detail.pdf_page_number IS NULL
    OR detail.pdf_page_number < 1
    OR detail.pdf_page_number > 5000
    OR detail.document_id IS NULL
    OR detail.version_id IS NULL
  THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;

  RETURN QUERY
  SELECT dv.storage_bucket, dv.storage_path, detail.pdf_page_number
  FROM app.document_versions AS dv
  INNER JOIN app.documents AS doc ON doc.id = detail.document_id
  WHERE dv.id = detail.version_id
    AND doc.current_version_id IS NOT DISTINCT FROM dv.id
    AND doc.deleted_at IS NULL
    AND dv.deleted_at IS NULL
    AND nullif(btrim(dv.storage_bucket), '') IS NOT NULL
    AND nullif(btrim(dv.storage_path), '') IS NOT NULL;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'query_admission:not_found';
  END IF;
END;
$fn$;

COMMENT ON FUNCTION app.get_citation_page_object_v1(
  uuid, text, bigint, uuid, uuid
) IS
  'Private storage location for one current authorized company-PDF page. Raises not_found when the citation is foreign, unavailable, or not a page. Does not return a signed URL.';

REVOKE ALL ON FUNCTION app.get_citation_page_object_v1(
  uuid, text, bigint, uuid, uuid
) FROM PUBLIC, anon, authenticated, app_worker;
GRANT EXECUTE ON FUNCTION app.get_citation_page_object_v1(
  uuid, text, bigint, uuid, uuid
) TO app_api;
