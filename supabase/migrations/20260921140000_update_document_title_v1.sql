-- Owner/admin document title rename. Additive. Does not change
-- delete_visible_document. SECURITY INVOKER: app_api receives column-level
-- UPDATE on title/updated_at only. Role checks stay inside the RPC.

GRANT UPDATE (title, updated_at) ON app.documents TO app_api;

DROP POLICY IF EXISTS documents_api_update_title ON app.documents;
CREATE POLICY documents_api_update_title
  ON app.documents
  FOR UPDATE
  TO app_api
  USING (deleted_at IS NULL)
  WITH CHECK (deleted_at IS NULL);

CREATE OR REPLACE FUNCTION app.sync_document_title_search_terms(
  p_document_id uuid,
  p_title text
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $sync$
DECLARE
  inserted integer := 0;
BEGIN
  INSERT INTO app.document_search_terms (chunk_id, term)
  SELECT c.id, p_title
  FROM app.documents AS d
  INNER JOIN app.document_chunks AS c
    ON c.document_id = d.id
   AND c.version_id IS NOT DISTINCT FROM d.current_version_id
  WHERE d.id = p_document_id
    AND d.deleted_at IS NULL
    AND c.deleted_at IS NULL
    AND c.is_search_representative
    AND p_title IS NOT NULL
    AND btrim(p_title) <> ''
    AND NOT EXISTS (
      SELECT 1
      FROM app.document_search_terms AS t
      WHERE t.chunk_id = c.id
        AND t.term_normalized = search.normalize_arabic_v1(p_title)
    );
  GET DIAGNOSTICS inserted = ROW_COUNT;
  RETURN inserted;
END;
$sync$;

COMMENT ON FUNCTION app.sync_document_title_search_terms(uuid, text) IS
  'Insert the current title as a search term on representative chunks. Does not re-parse or replace chunk ids.';

REVOKE ALL ON FUNCTION app.sync_document_title_search_terms(uuid, text)
  FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.sync_document_title_search_terms(uuid, text)
  TO app_api, app_worker;

CREATE OR REPLACE FUNCTION app.update_document_title(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_document_id uuid,
  p_title text
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  doc app.documents%ROWTYPE;
  safe_title text;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'documents:authorization_rejected';
  END IF;

  safe_title := btrim(COALESCE(p_title, ''));
  IF safe_title = '' OR char_length(safe_title) > 512 THEN
    RAISE EXCEPTION 'documents:invalid_title';
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

  UPDATE app.documents
  SET
    title = safe_title,
    updated_at = timezone('utc', now())
  WHERE id = doc.id;

  PERFORM app.sync_document_title_search_terms(doc.id, safe_title);

  PERFORM app.append_audit_event(
    'document.title_updated',
    caller_user_id,
    caller_role::app.user_role,
    'document',
    doc.id,
    app.current_authorization_version(),
    jsonb_build_object('title_chars', char_length(safe_title))
  );

  RETURN doc.id;
END;
$fn$;

COMMENT ON FUNCTION app.update_document_title(
  uuid, text, bigint, uuid, text
) IS
  'Owner/admin title rename. Unauthorized or deleted ids return NULL. Empty or over-long titles raise documents:invalid_title.';

REVOKE ALL ON FUNCTION app.update_document_title(
  uuid, text, bigint, uuid, text
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION app.update_document_title(
  uuid, text, bigint, uuid, text
) TO app_api;
