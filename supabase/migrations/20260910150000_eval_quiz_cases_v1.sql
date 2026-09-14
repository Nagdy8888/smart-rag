-- Hosted quiz-case labels and gold locators. Owner/admin app_api RPCs only.
-- Browser JWT roles never receive table DML. Holdout split is rejected.

CREATE TABLE app.eval_quiz_cases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  creator_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  reviewer_user_id uuid REFERENCES auth.users (id) ON DELETE SET NULL,
  source_run_id uuid REFERENCES app.runs (id) ON DELETE SET NULL,
  document_id uuid REFERENCES app.documents (id) ON DELETE SET NULL,
  version_id uuid REFERENCES app.document_versions (id) ON DELETE SET NULL,
  question text NOT NULL,
  expected_answer text NOT NULL DEFAULT '',
  atomic_facts text[] NOT NULL DEFAULT '{}'::text[],
  query_class text NOT NULL,
  required_terms text[] NOT NULL DEFAULT '{}'::text[],
  expected_profile_id text NOT NULL DEFAULT 'hybrid_default_v1',
  expected_scope text NOT NULL DEFAULT 'unscoped',
  expected_refusal boolean NOT NULL DEFAULT false,
  source_family_id text,
  split text NOT NULL,
  review_status text NOT NULL DEFAULT 'draft',
  generated_only boolean NOT NULL DEFAULT true,
  row_version integer NOT NULL DEFAULT 1,
  idempotency_key text NOT NULL,
  request_payload_hash text NOT NULL,
  reviewed_at timestamptz,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT eval_quiz_cases_question_chk CHECK (
    char_length(question) BETWEEN 1 AND 2000
  ),
  CONSTRAINT eval_quiz_cases_answer_chk CHECK (
    char_length(expected_answer) <= 8000
  ),
  CONSTRAINT eval_quiz_cases_facts_len_chk CHECK (
    cardinality(atomic_facts) <= 16
  ),
  CONSTRAINT eval_quiz_cases_terms_len_chk CHECK (
    cardinality(required_terms) <= 16
  ),
  CONSTRAINT eval_quiz_cases_class_chk CHECK (
    query_class IN (
      'factual_definition',
      'exact_acronym',
      'semantic_paraphrase',
      'multi_part',
      'section_scoped'
    )
  ),
  CONSTRAINT eval_quiz_cases_split_chk CHECK (
    split IN ('development', 'qualification')
  ),
  CONSTRAINT eval_quiz_cases_review_chk CHECK (
    review_status IN ('draft', 'approved', 'rejected')
  ),
  CONSTRAINT eval_quiz_cases_scope_chk CHECK (
    expected_scope IN ('unscoped', 'section', 'whole_document')
  ),
  CONSTRAINT eval_quiz_cases_profile_chk CHECK (
    expected_profile_id = 'hybrid_default_v1'
  ),
  CONSTRAINT eval_quiz_cases_refusal_chk CHECK (expected_refusal IS FALSE),
  CONSTRAINT eval_quiz_cases_family_chk CHECK (
    source_family_id IS NULL
    OR (
      char_length(source_family_id) BETWEEN 8 AND 128
      AND position('holdout' IN lower(source_family_id)) = 0
    )
  ),
  CONSTRAINT eval_quiz_cases_idempotency_chk CHECK (
    char_length(idempotency_key) BETWEEN 8 AND 128
  ),
  CONSTRAINT eval_quiz_cases_hash_chk CHECK (
    request_payload_hash ~ '^[0-9a-f]{64}$'
  ),
  CONSTRAINT eval_quiz_cases_row_version_chk CHECK (row_version >= 1),
  CONSTRAINT eval_quiz_cases_doc_pair_chk CHECK (
    (document_id IS NULL) = (version_id IS NULL)
  ),
  CONSTRAINT eval_quiz_cases_creator_idempotency_uq UNIQUE (
    creator_user_id,
    idempotency_key
  )
);

COMMENT ON TABLE app.eval_quiz_cases IS
  'Hosted evaluation questions and expected answers. Owner/admin RPCs only; 365-day expiry; max 60 live rows.';

CREATE TABLE app.eval_quiz_gold_chunks (
  case_id uuid NOT NULL REFERENCES app.eval_quiz_cases (id) ON DELETE CASCADE,
  ordinal integer NOT NULL,
  chunk_id uuid NOT NULL REFERENCES app.document_chunks (id) ON DELETE RESTRICT,
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE RESTRICT,
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE RESTRICT,
  page_number integer,
  page_label text,
  section_path text[] NOT NULL DEFAULT '{}'::text[],
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT eval_quiz_gold_chunks_pk PRIMARY KEY (case_id, ordinal),
  CONSTRAINT eval_quiz_gold_chunks_ordinal_chk CHECK (ordinal BETWEEN 1 AND 3),
  CONSTRAINT eval_quiz_gold_chunks_page_chk CHECK (
    page_number IS NULL OR page_number >= 1
  ),
  CONSTRAINT eval_quiz_gold_chunks_label_chk CHECK (
    page_label IS NULL OR char_length(page_label) BETWEEN 1 AND 64
  ),
  CONSTRAINT eval_quiz_gold_chunks_chunk_uq UNIQUE (case_id, chunk_id)
);

COMMENT ON TABLE app.eval_quiz_gold_chunks IS
  'Server-derived gold locators (0-3) for one quiz case. Client metadata is not trusted.';

CREATE INDEX eval_quiz_cases_expires_idx
  ON app.eval_quiz_cases (expires_at);

CREATE INDEX eval_quiz_cases_status_idx
  ON app.eval_quiz_cases (review_status, split, created_at DESC);

CREATE INDEX eval_quiz_gold_chunks_chunk_idx
  ON app.eval_quiz_gold_chunks (chunk_id);

CREATE OR REPLACE FUNCTION app.eval_quiz_cases_protect()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF TG_OP = 'UPDATE' AND NEW.split IS DISTINCT FROM OLD.split THEN
    RAISE EXCEPTION 'eval_quiz:split_immutable';
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key THEN
    RAISE EXCEPTION 'eval_quiz:idempotency_immutable';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM unnest(NEW.atomic_facts) AS fact(val)
    WHERE char_length(fact.val) < 1 OR char_length(fact.val) > 1000
  ) THEN
    RAISE EXCEPTION 'eval_quiz:facts_invalid';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM unnest(NEW.required_terms) AS term(val)
    WHERE char_length(term.val) < 1 OR char_length(term.val) > 200
  ) THEN
    RAISE EXCEPTION 'eval_quiz:terms_invalid';
  END IF;
  RETURN NEW;
END;
$fn$;

CREATE TRIGGER eval_quiz_cases_protect
  BEFORE INSERT OR UPDATE ON app.eval_quiz_cases
  FOR EACH ROW
  EXECUTE FUNCTION app.eval_quiz_cases_protect();

CREATE TRIGGER eval_quiz_cases_touch_updated_at
  BEFORE UPDATE ON app.eval_quiz_cases
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

ALTER TABLE app.eval_quiz_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.eval_quiz_cases FORCE ROW LEVEL SECURITY;
ALTER TABLE app.eval_quiz_gold_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.eval_quiz_gold_chunks FORCE ROW LEVEL SECURITY;

CREATE POLICY eval_quiz_cases_postgres_all
  ON app.eval_quiz_cases
  FOR ALL
  TO postgres
  USING (true)
  WITH CHECK (true);

CREATE POLICY eval_quiz_gold_chunks_postgres_all
  ON app.eval_quiz_gold_chunks
  FOR ALL
  TO postgres
  USING (true)
  WITH CHECK (true);

REVOKE ALL ON TABLE app.eval_quiz_cases FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON TABLE app.eval_quiz_gold_chunks FROM PUBLIC, anon, authenticated, app_api, app_worker;
GRANT ALL ON TABLE app.eval_quiz_cases TO postgres;
GRANT ALL ON TABLE app.eval_quiz_gold_chunks TO postgres;

CREATE OR REPLACE FUNCTION app._eval_quiz_require_owner_admin(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS void
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id,
    caller_role,
    caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'eval_quiz:authorization_rejected';
  END IF;
  IF caller_role NOT IN ('owner', 'admin') THEN
    RAISE EXCEPTION 'eval_quiz:forbidden';
  END IF;
END;
$fn$;

COMMENT ON FUNCTION app._eval_quiz_require_owner_admin(uuid, text, bigint) IS
  'Fail-closed owner/admin gate for hosted quiz RPCs.';

CREATE OR REPLACE FUNCTION app._eval_quiz_lock_workspace()
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM 1
  FROM app.company_settings AS cs
  WHERE cs.id = '00000000-0000-0000-0000-000000000001'::uuid
  FOR UPDATE;
END;
$fn$;

COMMENT ON FUNCTION app._eval_quiz_lock_workspace() IS
  'Serialize quiz-case capacity against the singleton company_settings row.';

CREATE OR REPLACE FUNCTION app._eval_quiz_chunk_page_label(p_provenance jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog, app
AS $$
  SELECT CASE
    WHEN jsonb_typeof(p_provenance -> 'locators') = 'array' THEN (
      SELECT left(nullif(btrim(loc ->> 'page_label'), ''), 64)
      FROM jsonb_array_elements(p_provenance -> 'locators') AS loc
      WHERE nullif(btrim(loc ->> 'page_label'), '') IS NOT NULL
      LIMIT 1
    )
    ELSE NULL
  END;
$$;

CREATE OR REPLACE FUNCTION app._eval_quiz_chunk_is_current(
  caller_user_id uuid,
  caller_role text,
  p_chunk_id uuid
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM app.document_chunks AS c
    INNER JOIN app.documents AS d ON d.id = c.document_id
    INNER JOIN app.document_versions AS v ON v.id = c.version_id
    WHERE c.id = p_chunk_id
      AND c.deleted_at IS NULL
      AND d.deleted_at IS NULL
      AND v.deleted_at IS NULL
      AND d.current_version_id IS NOT DISTINCT FROM c.version_id
      AND app.caller_can_read_document(caller_user_id, caller_role, d.id)
  );
$$;

CREATE OR REPLACE FUNCTION app._eval_quiz_audit(
  p_event_type text,
  p_actor_user_id uuid,
  p_actor_role text,
  p_target_id uuid,
  p_authorization_version bigint,
  p_payload jsonb
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  RETURN app.append_audit_event(
    p_event_type,
    p_actor_user_id,
    p_actor_role::app.user_role,
    'eval_quiz_case',
    p_target_id,
    p_authorization_version,
    COALESCE(p_payload, '{}'::jsonb)
  );
END;
$fn$;

CREATE OR REPLACE FUNCTION app._eval_quiz_assert_family(
  p_source_family_id text,
  p_split text,
  p_case_id uuid
)
RETURNS void
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF p_source_family_id IS NULL OR btrim(p_source_family_id) = '' THEN
    RETURN;
  END IF;
  IF EXISTS (
    SELECT 1
    FROM app.eval_quiz_cases AS c
    WHERE c.source_family_id = p_source_family_id
      AND c.split IS DISTINCT FROM p_split
      AND c.expires_at > timezone('utc', now())
      AND (p_case_id IS NULL OR c.id IS DISTINCT FROM p_case_id)
  ) THEN
    RAISE EXCEPTION 'eval_quiz:family_split_conflict';
  END IF;
END;
$fn$;

CREATE OR REPLACE FUNCTION app._eval_quiz_apply_gold(
  p_case_id uuid,
  p_chunk_ids uuid[],
  caller_user_id uuid,
  caller_role text
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_ids uuid[];
  v_chunk uuid;
  v_ordinal integer := 0;
  v_document uuid;
  v_version uuid;
  v_chunk_document uuid;
  v_chunk_version uuid;
  v_page integer;
  v_label text;
  v_path text[];
BEGIN
  DELETE FROM app.eval_quiz_gold_chunks WHERE case_id = p_case_id;

  v_ids := COALESCE(p_chunk_ids, '{}'::uuid[]);
  IF cardinality(v_ids) > 3 THEN
    RAISE EXCEPTION 'eval_quiz:gold_limit';
  END IF;

  FOREACH v_chunk IN ARRAY v_ids
  LOOP
    v_ordinal := v_ordinal + 1;
    IF v_chunk IS NULL THEN
      RAISE EXCEPTION 'eval_quiz:not_found';
    END IF;
    IF NOT app._eval_quiz_chunk_is_current(caller_user_id, caller_role, v_chunk) THEN
      RAISE EXCEPTION 'eval_quiz:not_found';
    END IF;

    SELECT c.document_id, c.version_id, c.page_number,
           app._eval_quiz_chunk_page_label(c.provenance),
           c.section_path
    INTO v_chunk_document, v_chunk_version, v_page, v_label, v_path
    FROM app.document_chunks AS c
    WHERE c.id = v_chunk;

    IF v_document IS NULL THEN
      v_document := v_chunk_document;
      v_version := v_chunk_version;
    ELSIF v_document IS DISTINCT FROM v_chunk_document
      OR v_version IS DISTINCT FROM v_chunk_version THEN
      RAISE EXCEPTION 'eval_quiz:gold_version_mismatch';
    END IF;

    INSERT INTO app.eval_quiz_gold_chunks (
      case_id, ordinal, chunk_id, document_id, version_id,
      page_number, page_label, section_path
    )
    VALUES (
      p_case_id, v_ordinal, v_chunk, v_chunk_document, v_chunk_version,
      v_page, v_label, COALESCE(v_path, '{}'::text[])
    );
  END LOOP;

  IF v_ordinal = 0 THEN
    UPDATE app.eval_quiz_cases
    SET document_id = NULL, version_id = NULL
    WHERE id = p_case_id;
  ELSE
    UPDATE app.eval_quiz_cases
    SET document_id = v_document, version_id = v_version
    WHERE id = p_case_id;
  END IF;
EXCEPTION
  WHEN unique_violation THEN
    RAISE EXCEPTION 'eval_quiz:gold_duplicate';
END;
$fn$;

CREATE OR REPLACE FUNCTION app.create_eval_quiz_case(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_source_run_id uuid,
  p_question text,
  p_expected_answer text,
  p_atomic_facts text[],
  p_query_class text,
  p_required_terms text[],
  p_split text,
  p_source_family_id text,
  p_generated_only boolean,
  p_chunk_ids uuid[],
  p_idempotency_key text,
  p_request_payload_hash text
)
RETURNS TABLE (
  case_id uuid,
  row_version integer,
  replayed boolean
)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_question text;
  v_split text;
  v_family text;
  v_existing app.eval_quiz_cases%ROWTYPE;
  v_id uuid;
  v_live integer;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );

  IF p_split IS NOT NULL AND lower(p_split) = 'holdout' THEN
    RAISE EXCEPTION 'eval_quiz:holdout_rejected';
  END IF;
  v_split := COALESCE(NULLIF(btrim(p_split), ''), 'development');
  IF v_split NOT IN ('development', 'qualification') THEN
    RAISE EXCEPTION 'eval_quiz:holdout_rejected';
  END IF;
  IF p_query_class IS NULL OR p_query_class NOT IN (
    'factual_definition',
    'exact_acronym',
    'semantic_paraphrase',
    'multi_part',
    'section_scoped'
  ) THEN
    RAISE EXCEPTION 'eval_quiz:class_invalid';
  END IF;

  v_family := NULLIF(btrim(COALESCE(p_source_family_id, '')), '');

  PERFORM app._eval_quiz_lock_workspace();

  SELECT * INTO v_existing
  FROM app.eval_quiz_cases AS c
  WHERE c.creator_user_id = caller_user_id
    AND c.idempotency_key = p_idempotency_key;

  IF FOUND THEN
    IF v_existing.expires_at <= timezone('utc', now()) THEN
      DELETE FROM app.eval_quiz_cases WHERE id = v_existing.id;
    ELSIF v_existing.request_payload_hash = p_request_payload_hash THEN
      case_id := v_existing.id;
      row_version := v_existing.row_version;
      replayed := true;
      RETURN NEXT;
      RETURN;
    ELSE
      RAISE EXCEPTION 'eval_quiz:idempotency_collision';
    END IF;
  END IF;

  IF p_source_run_id IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1
      FROM app.runs AS r
      INNER JOIN app.conversations AS c ON c.id = r.conversation_id
      WHERE r.id = p_source_run_id
        AND r.creator_user_id = caller_user_id
        AND r.status = 'completed'::app.run_status
        AND c.deleted_at IS NULL
    ) THEN
      RAISE EXCEPTION 'eval_quiz:not_found';
    END IF;
    SELECT m.content INTO v_question
    FROM app.load_query_run_user_message(
      caller_user_id, caller_role, caller_authorization_version, p_source_run_id
    ) AS m;
    IF v_question IS NULL OR btrim(v_question) = '' THEN
      RAISE EXCEPTION 'eval_quiz:not_found';
    END IF;
  ELSE
    v_question := NULLIF(btrim(COALESCE(p_question, '')), '');
    IF v_question IS NULL THEN
      RAISE EXCEPTION 'eval_quiz:question_invalid';
    END IF;
  END IF;

  IF char_length(v_question) > 2000 THEN
    RAISE EXCEPTION 'eval_quiz:question_invalid';
  END IF;

  PERFORM app._eval_quiz_assert_family(v_family, v_split, NULL);

  SELECT count(*)::integer INTO v_live
  FROM app.eval_quiz_cases AS c
  WHERE c.expires_at > timezone('utc', now());
  IF v_live >= 60 THEN
    RAISE EXCEPTION 'eval_quiz:capacity_exceeded';
  END IF;

  INSERT INTO app.eval_quiz_cases (
    creator_user_id,
    source_run_id,
    question,
    expected_answer,
    atomic_facts,
    query_class,
    required_terms,
    source_family_id,
    split,
    review_status,
    generated_only,
    idempotency_key,
    request_payload_hash,
    expires_at
  )
  VALUES (
    caller_user_id,
    p_source_run_id,
    v_question,
    left(COALESCE(p_expected_answer, ''), 8000),
    COALESCE(p_atomic_facts, '{}'::text[]),
    p_query_class,
    COALESCE(p_required_terms, '{}'::text[]),
    v_family,
    v_split,
    'draft',
    COALESCE(p_generated_only, true),
    p_idempotency_key,
    lower(p_request_payload_hash),
    timezone('utc', now()) + interval '365 days'
  )
  RETURNING id INTO v_id;

  PERFORM app._eval_quiz_apply_gold(
    v_id, COALESCE(p_chunk_ids, '{}'::uuid[]), caller_user_id, caller_role
  );

  PERFORM app._eval_quiz_audit(
    'eval_quiz_case_create',
    caller_user_id,
    caller_role,
    v_id,
    caller_authorization_version,
    jsonb_build_object(
      'split', v_split,
      'generated_only', COALESCE(p_generated_only, true),
      'gold_count', cardinality(COALESCE(p_chunk_ids, '{}'::uuid[])),
      'replayed', false
    )
  );

  case_id := v_id;
  row_version := 1;
  replayed := false;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.create_eval_quiz_case(
  uuid, text, bigint, uuid, text, text, text[], text, text[], text, text, boolean, uuid[], text, text
) IS
  'Create a draft quiz case. Question comes from a caller-owned completed run when source_run_id is set.';

CREATE OR REPLACE FUNCTION app.list_eval_quiz_case_summaries(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_split text,
  p_review_status text,
  p_limit integer,
  p_after_id uuid
)
RETURNS TABLE (
  case_id uuid,
  split text,
  query_class text,
  review_status text,
  generated_only boolean,
  source_family_id text,
  gold_chunk_count integer,
  gold_stale boolean,
  row_version integer,
  created_at timestamptz,
  expires_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  bounded_limit integer;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  IF p_split IS NOT NULL AND lower(p_split) = 'holdout' THEN
    RAISE EXCEPTION 'eval_quiz:holdout_rejected';
  END IF;
  bounded_limit := LEAST(GREATEST(COALESCE(p_limit, 20), 1), 20);

  RETURN QUERY
  SELECT
    c.id,
    c.split,
    c.query_class,
    c.review_status,
    c.generated_only,
    c.source_family_id,
    (
      SELECT count(*)::integer
      FROM app.eval_quiz_gold_chunks AS g
      WHERE g.case_id = c.id
    ),
    EXISTS (
      SELECT 1
      FROM app.eval_quiz_gold_chunks AS g
      WHERE g.case_id = c.id
        AND NOT app._eval_quiz_chunk_is_current(
          caller_user_id, caller_role, g.chunk_id
        )
    ),
    c.row_version,
    c.created_at,
    c.expires_at
  FROM app.eval_quiz_cases AS c
  WHERE c.expires_at > timezone('utc', now())
    AND (p_split IS NULL OR c.split = p_split)
    AND (p_review_status IS NULL OR c.review_status = p_review_status)
    AND (
      p_after_id IS NULL
      OR (c.created_at, c.id) < (
        SELECT inner_c.created_at, inner_c.id
        FROM app.eval_quiz_cases AS inner_c
        WHERE inner_c.id = p_after_id
      )
    )
  ORDER BY c.created_at DESC, c.id DESC
  LIMIT bounded_limit;
END;
$fn$;

COMMENT ON FUNCTION app.list_eval_quiz_case_summaries(
  uuid, text, bigint, text, text, integer, uuid
) IS
  'Owner/admin quiz summaries without questions, answers, facts, or excerpts.';

CREATE OR REPLACE FUNCTION app.get_eval_quiz_case(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_case_id uuid
)
RETURNS TABLE (
  case_id uuid,
  split text,
  query_class text,
  review_status text,
  generated_only boolean,
  source_family_id text,
  question text,
  expected_answer text,
  atomic_facts text[],
  required_terms text[],
  expected_scope text,
  source_run_id uuid,
  document_id uuid,
  version_id uuid,
  gold jsonb,
  gold_stale boolean,
  reviewer_user_id uuid,
  reviewed_at timestamptz,
  row_version integer,
  created_at timestamptz,
  expires_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_case app.eval_quiz_cases%ROWTYPE;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  SELECT * INTO v_case
  FROM app.eval_quiz_cases AS c
  WHERE c.id = p_case_id
    AND c.expires_at > timezone('utc', now());
  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_quiz:not_found';
  END IF;

  case_id := v_case.id;
  split := v_case.split;
  query_class := v_case.query_class;
  review_status := v_case.review_status;
  generated_only := v_case.generated_only;
  source_family_id := v_case.source_family_id;
  question := v_case.question;
  expected_answer := v_case.expected_answer;
  atomic_facts := v_case.atomic_facts;
  required_terms := v_case.required_terms;
  expected_scope := v_case.expected_scope;
  source_run_id := v_case.source_run_id;
  document_id := v_case.document_id;
  version_id := v_case.version_id;
  SELECT coalesce(
    jsonb_agg(
      jsonb_build_object(
        'ordinal', g.ordinal,
        'chunk_id', g.chunk_id,
        'document_id', g.document_id,
        'version_id', g.version_id,
        'page_number', g.page_number,
        'page_label', g.page_label,
        'section_path', to_jsonb(g.section_path),
        'stale', NOT app._eval_quiz_chunk_is_current(
          caller_user_id, caller_role, g.chunk_id
        )
      )
      ORDER BY g.ordinal
    ),
    '[]'::jsonb
  )
  INTO gold
  FROM app.eval_quiz_gold_chunks AS g
  WHERE g.case_id = v_case.id;
  gold_stale := EXISTS (
    SELECT 1
    FROM app.eval_quiz_gold_chunks AS g
    WHERE g.case_id = v_case.id
      AND NOT app._eval_quiz_chunk_is_current(
        caller_user_id, caller_role, g.chunk_id
      )
  );
  reviewer_user_id := v_case.reviewer_user_id;
  reviewed_at := v_case.reviewed_at;
  row_version := v_case.row_version;
  created_at := v_case.created_at;
  expires_at := v_case.expires_at;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.get_eval_quiz_case(uuid, text, bigint, uuid) IS
  'Owner/admin quiz detail. Callers must not log question or answer text.';

CREATE OR REPLACE FUNCTION app.patch_eval_quiz_case(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_case_id uuid,
  p_row_version integer,
  p_question text,
  p_expected_answer text,
  p_atomic_facts text[],
  p_query_class text,
  p_required_terms text[],
  p_source_family_id text,
  p_expected_scope text
)
RETURNS TABLE (case_id uuid, row_version integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_case app.eval_quiz_cases%ROWTYPE;
  v_family text;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  PERFORM app._eval_quiz_lock_workspace();

  SELECT * INTO v_case
  FROM app.eval_quiz_cases AS c
  WHERE c.id = p_case_id
    AND c.expires_at > timezone('utc', now());
  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_quiz:not_found';
  END IF;
  IF v_case.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'eval_quiz:stale_row_version';
  END IF;

  v_family := COALESCE(
    NULLIF(btrim(COALESCE(p_source_family_id, '')), ''),
    v_case.source_family_id
  );
  PERFORM app._eval_quiz_assert_family(v_family, v_case.split, v_case.id);

  UPDATE app.eval_quiz_cases AS c
  SET
    question = COALESCE(NULLIF(btrim(COALESCE(p_question, '')), ''), c.question),
    expected_answer = COALESCE(p_expected_answer, c.expected_answer),
    atomic_facts = COALESCE(p_atomic_facts, c.atomic_facts),
    query_class = COALESCE(NULLIF(btrim(COALESCE(p_query_class, '')), ''), c.query_class),
    required_terms = COALESCE(p_required_terms, c.required_terms),
    source_family_id = v_family,
    expected_scope = COALESCE(
      NULLIF(btrim(COALESCE(p_expected_scope, '')), ''),
      c.expected_scope
    ),
    review_status = 'draft',
    reviewer_user_id = NULL,
    reviewed_at = NULL,
    generated_only = false,
    row_version = c.row_version + 1
  WHERE c.id = p_case_id
  RETURNING c.id, c.row_version INTO case_id, row_version;

  PERFORM app._eval_quiz_audit(
    'eval_quiz_case_patch',
    caller_user_id,
    caller_role,
    p_case_id,
    caller_authorization_version,
    jsonb_build_object('row_version', row_version)
  );
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.patch_eval_quiz_case(
  uuid, text, bigint, uuid, integer, text, text, text[], text, text[], text, text
) IS
  'CAS content edit. Resets approval, reviewer, and reviewed_at.';

CREATE OR REPLACE FUNCTION app.replace_eval_quiz_gold(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_case_id uuid,
  p_row_version integer,
  p_chunk_ids uuid[]
)
RETURNS TABLE (case_id uuid, row_version integer, gold_chunk_count integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_case app.eval_quiz_cases%ROWTYPE;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  PERFORM app._eval_quiz_lock_workspace();

  SELECT * INTO v_case
  FROM app.eval_quiz_cases AS c
  WHERE c.id = p_case_id
    AND c.expires_at > timezone('utc', now());
  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_quiz:not_found';
  END IF;
  IF v_case.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'eval_quiz:stale_row_version';
  END IF;

  PERFORM app._eval_quiz_apply_gold(
    p_case_id, COALESCE(p_chunk_ids, '{}'::uuid[]), caller_user_id, caller_role
  );

  UPDATE app.eval_quiz_cases AS c
  SET
    review_status = 'draft',
    reviewer_user_id = NULL,
    reviewed_at = NULL,
    generated_only = false,
    row_version = c.row_version + 1
  WHERE c.id = p_case_id
  RETURNING c.id, c.row_version INTO case_id, row_version;

  gold_chunk_count := cardinality(COALESCE(p_chunk_ids, '{}'::uuid[]));
  PERFORM app._eval_quiz_audit(
    'eval_quiz_gold_replace',
    caller_user_id,
    caller_role,
    p_case_id,
    caller_authorization_version,
    jsonb_build_object(
      'row_version', row_version,
      'gold_count', gold_chunk_count
    )
  );
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.replace_eval_quiz_gold(
  uuid, text, bigint, uuid, integer, uuid[]
) IS
  'Replace gold locators from current authorized chunk IDs. Resets approval.';

CREATE OR REPLACE FUNCTION app.approve_eval_quiz_case(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_case_id uuid,
  p_row_version integer
)
RETURNS TABLE (case_id uuid, row_version integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_case app.eval_quiz_cases%ROWTYPE;
  v_gold integer;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  PERFORM app._eval_quiz_lock_workspace();

  SELECT * INTO v_case
  FROM app.eval_quiz_cases AS c
  WHERE c.id = p_case_id
    AND c.expires_at > timezone('utc', now());
  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_quiz:not_found';
  END IF;
  IF v_case.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'eval_quiz:stale_row_version';
  END IF;
  IF btrim(v_case.expected_answer) = '' THEN
    RAISE EXCEPTION 'eval_quiz:answer_required';
  END IF;
  IF v_case.source_family_id IS NULL THEN
    RAISE EXCEPTION 'eval_quiz:family_required';
  END IF;
  PERFORM app._eval_quiz_assert_family(
    v_case.source_family_id, v_case.split, v_case.id
  );

  SELECT count(*)::integer INTO v_gold
  FROM app.eval_quiz_gold_chunks AS g
  WHERE g.case_id = v_case.id;
  IF v_gold < 1 OR v_gold > 3 THEN
    RAISE EXCEPTION 'eval_quiz:gold_required';
  END IF;
  IF EXISTS (
    SELECT 1
    FROM app.eval_quiz_gold_chunks AS g
    WHERE g.case_id = v_case.id
      AND (
        g.document_id IS DISTINCT FROM v_case.document_id
        OR g.version_id IS DISTINCT FROM v_case.version_id
        OR NOT app._eval_quiz_chunk_is_current(
          caller_user_id, caller_role, g.chunk_id
        )
      )
  ) THEN
    RAISE EXCEPTION 'eval_quiz:gold_stale';
  END IF;

  UPDATE app.eval_quiz_cases AS c
  SET
    review_status = 'approved',
    generated_only = false,
    reviewer_user_id = caller_user_id,
    reviewed_at = timezone('utc', now()),
    row_version = c.row_version + 1
  WHERE c.id = p_case_id
  RETURNING c.id, c.row_version INTO case_id, row_version;

  PERFORM app._eval_quiz_audit(
    'eval_quiz_case_approve',
    caller_user_id,
    caller_role,
    p_case_id,
    caller_authorization_version,
    jsonb_build_object('row_version', row_version, 'gold_count', v_gold)
  );
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.approve_eval_quiz_case(uuid, text, bigint, uuid, integer) IS
  'Named-human approval. Requires answer, source family, and one to three current gold chunks.';

CREATE OR REPLACE FUNCTION app.reject_eval_quiz_case(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_case_id uuid,
  p_row_version integer
)
RETURNS TABLE (case_id uuid, row_version integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_case app.eval_quiz_cases%ROWTYPE;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );

  SELECT * INTO v_case
  FROM app.eval_quiz_cases AS c
  WHERE c.id = p_case_id
    AND c.expires_at > timezone('utc', now());
  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_quiz:not_found';
  END IF;
  IF v_case.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'eval_quiz:stale_row_version';
  END IF;

  UPDATE app.eval_quiz_cases AS c
  SET
    review_status = 'rejected',
    generated_only = false,
    reviewer_user_id = caller_user_id,
    reviewed_at = timezone('utc', now()),
    row_version = c.row_version + 1
  WHERE c.id = p_case_id
  RETURNING c.id, c.row_version INTO case_id, row_version;

  PERFORM app._eval_quiz_audit(
    'eval_quiz_case_reject',
    caller_user_id,
    caller_role,
    p_case_id,
    caller_authorization_version,
    jsonb_build_object('row_version', row_version)
  );
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.reject_eval_quiz_case(uuid, text, bigint, uuid, integer) IS
  'Named-human reject. Content-free audit only.';

CREATE OR REPLACE FUNCTION app.delete_eval_quiz_case(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_case_id uuid,
  p_row_version integer
)
RETURNS TABLE (deleted boolean)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_case app.eval_quiz_cases%ROWTYPE;
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );

  SELECT * INTO v_case
  FROM app.eval_quiz_cases AS c
  WHERE c.id = p_case_id;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'eval_quiz:not_found';
  END IF;
  IF v_case.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'eval_quiz:stale_row_version';
  END IF;

  DELETE FROM app.eval_quiz_cases WHERE id = p_case_id;
  PERFORM app._eval_quiz_audit(
    'eval_quiz_case_delete',
    caller_user_id,
    caller_role,
    p_case_id,
    caller_authorization_version,
    jsonb_build_object('row_version', p_row_version)
  );
  deleted := true;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.delete_eval_quiz_case(uuid, text, bigint, uuid, integer) IS
  'Immediate quiz-case delete with content-free audit.';

CREATE OR REPLACE FUNCTION app.count_eval_quiz_case_status(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  draft_count integer,
  approved_count integer,
  rejected_count integer,
  stale_gold_count integer,
  live_count integer,
  remaining_capacity integer
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );

  SELECT
    count(*) FILTER (WHERE c.review_status = 'draft')::integer,
    count(*) FILTER (WHERE c.review_status = 'approved')::integer,
    count(*) FILTER (WHERE c.review_status = 'rejected')::integer,
    count(*) FILTER (
      WHERE EXISTS (
        SELECT 1
        FROM app.eval_quiz_gold_chunks AS g
        WHERE g.case_id = c.id
          AND NOT app._eval_quiz_chunk_is_current(
            caller_user_id, caller_role, g.chunk_id
          )
      )
    )::integer,
    count(*)::integer,
    GREATEST(60 - count(*)::integer, 0)
  INTO
    draft_count,
    approved_count,
    rejected_count,
    stale_gold_count,
    live_count,
    remaining_capacity
  FROM app.eval_quiz_cases AS c
  WHERE c.expires_at > timezone('utc', now());
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.count_eval_quiz_case_status(uuid, text, bigint) IS
  'Aggregate quiz counts without questions or gold UUID lists.';

CREATE OR REPLACE FUNCTION app.purge_expired_eval_quiz_cases(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (purged_count integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_ids uuid[];
BEGIN
  PERFORM app._eval_quiz_require_owner_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  PERFORM app._eval_quiz_lock_workspace();

  SELECT coalesce(array_agg(c.id), '{}'::uuid[])
  INTO v_ids
  FROM (
    SELECT c.id
    FROM app.eval_quiz_cases AS c
    WHERE c.expires_at <= timezone('utc', now())
    ORDER BY c.expires_at ASC
    LIMIT 60
  ) AS c;

  DELETE FROM app.eval_quiz_cases WHERE id = ANY (v_ids);
  purged_count := cardinality(v_ids);
  IF purged_count > 0 THEN
    PERFORM app._eval_quiz_audit(
      'eval_quiz_case_purge',
      caller_user_id,
      caller_role,
      NULL,
      caller_authorization_version,
      jsonb_build_object('purged_count', purged_count)
    );
  END IF;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.purge_expired_eval_quiz_cases(uuid, text, bigint) IS
  'Bounded content-free purge of expired quiz rows (max 60 per call).';

REVOKE ALL ON FUNCTION app._eval_quiz_require_owner_admin(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_quiz_lock_workspace()
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_quiz_chunk_page_label(jsonb)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_quiz_chunk_is_current(uuid, text, uuid)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_quiz_audit(text, uuid, text, uuid, bigint, jsonb)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_quiz_assert_family(text, text, uuid)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app._eval_quiz_apply_gold(uuid, uuid[], uuid, text)
  FROM PUBLIC, anon, authenticated, app_api, app_worker;
REVOKE ALL ON FUNCTION app.eval_quiz_cases_protect()
  FROM PUBLIC, anon, authenticated, app_api, app_worker;

REVOKE ALL ON FUNCTION app.create_eval_quiz_case(
  uuid, text, bigint, uuid, text, text, text[], text, text[], text, text, boolean, uuid[], text, text
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.list_eval_quiz_case_summaries(
  uuid, text, bigint, text, text, integer, uuid
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.get_eval_quiz_case(uuid, text, bigint, uuid)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.patch_eval_quiz_case(
  uuid, text, bigint, uuid, integer, text, text, text[], text, text[], text, text
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.replace_eval_quiz_gold(
  uuid, text, bigint, uuid, integer, uuid[]
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.approve_eval_quiz_case(uuid, text, bigint, uuid, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.reject_eval_quiz_case(uuid, text, bigint, uuid, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.delete_eval_quiz_case(uuid, text, bigint, uuid, integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.count_eval_quiz_case_status(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION app.purge_expired_eval_quiz_cases(uuid, text, bigint)
  FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION app.create_eval_quiz_case(
  uuid, text, bigint, uuid, text, text, text[], text, text[], text, text, boolean, uuid[], text, text
) TO app_api;
GRANT EXECUTE ON FUNCTION app.list_eval_quiz_case_summaries(
  uuid, text, bigint, text, text, integer, uuid
) TO app_api;
GRANT EXECUTE ON FUNCTION app.get_eval_quiz_case(uuid, text, bigint, uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.patch_eval_quiz_case(
  uuid, text, bigint, uuid, integer, text, text, text[], text, text[], text, text
) TO app_api;
GRANT EXECUTE ON FUNCTION app.replace_eval_quiz_gold(
  uuid, text, bigint, uuid, integer, uuid[]
) TO app_api;
GRANT EXECUTE ON FUNCTION app.approve_eval_quiz_case(uuid, text, bigint, uuid, integer)
  TO app_api;
GRANT EXECUTE ON FUNCTION app.reject_eval_quiz_case(uuid, text, bigint, uuid, integer)
  TO app_api;
GRANT EXECUTE ON FUNCTION app.delete_eval_quiz_case(uuid, text, bigint, uuid, integer)
  TO app_api;
GRANT EXECUTE ON FUNCTION app.count_eval_quiz_case_status(uuid, text, bigint)
  TO app_api;
GRANT EXECUTE ON FUNCTION app.purge_expired_eval_quiz_cases(uuid, text, bigint)
  TO app_api;
