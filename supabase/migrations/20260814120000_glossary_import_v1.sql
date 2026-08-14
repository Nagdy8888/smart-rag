-- Phase 4 Packet 1: owner/admin glossary import, approval, rollback, and
-- additive search_aliases projection columns. Private glossary values are not
-- stored in Git. Audit payloads record counts and ids only.

CREATE TYPE app.glossary_import_status AS ENUM (
  'pending_approval',
  'approved',
  'rolled_back',
  'rejected'
);

CREATE TYPE app.glossary_entry_type AS ENUM (
  'product_code',
  'project_name',
  'acronym',
  'canonical_term',
  'identifier_rule'
);

CREATE TABLE app.glossary_imports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_name text NOT NULL,
  source_version text NOT NULL,
  idempotency_key text NOT NULL,
  status app.glossary_import_status NOT NULL,
  imported_by uuid NOT NULL REFERENCES app.profiles (user_id),
  approved_by uuid REFERENCES app.profiles (user_id),
  approved_at timestamptz,
  rolled_back_by uuid REFERENCES app.profiles (user_id),
  rolled_back_at timestamptz,
  entry_count integer NOT NULL DEFAULT 0,
  alias_count integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT glossary_imports_idempotency_key_uq UNIQUE (idempotency_key),
  CONSTRAINT glossary_imports_counts_nonnegative CHECK (
    entry_count >= 0 AND alias_count >= 0
  )
);

COMMENT ON TABLE app.glossary_imports IS
  'Owner/admin glossary import batches. Search projection occurs only after approval.';

CREATE TABLE app.glossary_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_id uuid NOT NULL REFERENCES app.glossary_imports (id) ON DELETE CASCADE,
  entry_key text NOT NULL,
  canonical_term text NOT NULL,
  term_normalized text GENERATED ALWAYS AS (search.normalize_arabic_v1(canonical_term)) STORED,
  language text NOT NULL,
  entry_type app.glossary_entry_type NOT NULL,
  effective_scope text NOT NULL,
  identifier_pattern text,
  checksum_algorithm text,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT glossary_entries_language_chk CHECK (language IN ('en', 'ar', 'mixed')),
  CONSTRAINT glossary_entries_scope_chk CHECK (
    effective_scope IN ('company', 'synthetic_eval')
  ),
  CONSTRAINT glossary_entries_import_key_uq UNIQUE (import_id, entry_key)
);

COMMENT ON TABLE app.glossary_entries IS
  'Canonical glossary terms for an import. Values are application-private.';

CREATE TABLE app.glossary_aliases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entry_id uuid NOT NULL REFERENCES app.glossary_entries (id) ON DELETE CASCADE,
  alias text NOT NULL,
  alias_normalized text GENERATED ALWAYS AS (search.normalize_arabic_v1(alias)) STORED,
  language text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT glossary_aliases_language_chk CHECK (language IN ('en', 'ar', 'mixed'))
);

COMMENT ON TABLE app.glossary_aliases IS
  'Aliases for canonical glossary entries. Not projected until import approval.';

ALTER TABLE app.search_aliases
  ADD COLUMN IF NOT EXISTS glossary_entry_id uuid REFERENCES app.glossary_entries (id)
    ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS import_id uuid REFERENCES app.glossary_imports (id)
    ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS language text,
  ADD COLUMN IF NOT EXISTS effective_scope text;

CREATE INDEX glossary_aliases_entry_id_idx
  ON app.glossary_aliases (entry_id);

CREATE INDEX glossary_aliases_normalized_idx
  ON app.glossary_aliases (alias_normalized);

CREATE INDEX glossary_entries_import_id_idx
  ON app.glossary_entries (import_id);

CREATE INDEX search_aliases_import_id_idx
  ON app.search_aliases (import_id);

CREATE TRIGGER glossary_imports_touch_updated_at
  BEFORE UPDATE ON app.glossary_imports
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

ALTER TABLE app.glossary_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.glossary_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.glossary_aliases ENABLE ROW LEVEL SECURITY;

CREATE POLICY glossary_imports_worker_read ON app.glossary_imports
  FOR SELECT
  TO app_worker
  USING (true);

CREATE POLICY glossary_entries_worker_read ON app.glossary_entries
  FOR SELECT
  TO app_worker
  USING (true);

CREATE POLICY glossary_aliases_worker_read ON app.glossary_aliases
  FOR SELECT
  TO app_worker
  USING (true);

GRANT SELECT ON app.glossary_imports TO app_worker;
GRANT SELECT ON app.glossary_entries TO app_worker;
GRANT SELECT ON app.glossary_aliases TO app_worker;

CREATE OR REPLACE FUNCTION app.glossary_identifier_rule_rejected(pattern text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
STRICT
SET search_path = pg_catalog
AS $$
  SELECT
    pattern IS NULL
    OR btrim(pattern) = ''
    OR pattern ~ '\\d\{1,3\}'
    OR (
      pattern ~ '\\.\\*|\\.\\+|\\\\w\\+|\\\\S\\+'
      AND length(regexp_replace(pattern, '[.^$*+?{}\\[\\]\\\\|()].*$', '')) < 4
    );
$$;

COMMENT ON FUNCTION app.glossary_identifier_rule_rejected(text) IS
  'Rejects high-collision identifier patterns. Reason codes only; no corpus text.';

CREATE OR REPLACE FUNCTION app.glossary_payload_has_cycle(payload jsonb)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, search, app
AS $fn$
DECLARE
  cycle_found boolean := false;
BEGIN
  WITH RECURSIVE edges AS (
    SELECT
      search.normalize_arabic_v1(alias_elem ->> 'alias') AS src,
      search.normalize_arabic_v1(entry_elem ->> 'canonical_term') AS dst
    FROM jsonb_array_elements(payload -> 'entries') AS entry_elem
    CROSS JOIN LATERAL jsonb_array_elements(
      COALESCE(entry_elem -> 'aliases', '[]'::jsonb)
    ) AS alias_elem
    WHERE COALESCE(alias_elem ->> 'alias', '') <> ''
  ),
  walk AS (
    SELECT src, dst, ARRAY[src, dst] AS seen, 1 AS depth
    FROM edges
    UNION ALL
    SELECT walk.src, edges.dst, walk.seen || edges.dst, walk.depth + 1
    FROM walk
    JOIN edges ON edges.src = walk.dst
    WHERE walk.depth < 32
      AND NOT edges.dst = ANY (walk.seen)
  )
  SELECT EXISTS (
    SELECT 1
    FROM walk
    JOIN edges ON edges.src = walk.dst AND edges.dst = ANY (walk.seen)
  ) INTO cycle_found;
  RETURN COALESCE(cycle_found, false);
END;
$fn$;

COMMENT ON FUNCTION app.glossary_payload_has_cycle(jsonb) IS
  'Detects alias-to-canonical cycles in an import payload.';

CREATE OR REPLACE FUNCTION app.import_glossary_batch(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  source_name text,
  source_version text,
  idempotency_key text,
  payload jsonb
)
RETURNS TABLE (
  import_id uuid,
  status app.glossary_import_status,
  entry_count integer,
  alias_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  existing app.glossary_imports%ROWTYPE;
  new_import_id uuid;
  new_entry_count integer := 0;
  new_alias_count integer := 0;
  entry_elem jsonb;
  alias_elem jsonb;
  new_entry_id uuid;
  canonical_norm text;
  alias_norm text;
  entry_rec record;
  alias_rec record;
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

  IF source_name IS NULL OR btrim(source_name) = '' THEN
    RAISE EXCEPTION 'source_name required';
  END IF;

  IF source_version IS NULL OR btrim(source_version) = '' THEN
    RAISE EXCEPTION 'source_version required';
  END IF;

  IF idempotency_key IS NULL OR btrim(idempotency_key) = '' THEN
    RAISE EXCEPTION 'idempotency_key required';
  END IF;

  IF payload IS NULL OR jsonb_typeof(payload -> 'entries') IS DISTINCT FROM 'array' THEN
    RAISE EXCEPTION 'payload entries required';
  END IF;

  IF jsonb_array_length(payload -> 'entries') < 1
     OR jsonb_array_length(payload -> 'entries') > 500 THEN
    RAISE EXCEPTION 'payload entry bounds';
  END IF;

  SELECT * INTO existing
  FROM app.glossary_imports AS gi
  WHERE gi.idempotency_key = import_glossary_batch.idempotency_key;

  IF FOUND THEN
    import_id := existing.id;
    status := existing.status;
    entry_count := existing.entry_count;
    alias_count := existing.alias_count;
    RETURN NEXT;
    RETURN;
  END IF;

  IF app.glossary_payload_has_cycle(payload) THEN
    RAISE EXCEPTION 'alias_cycle';
  END IF;

  INSERT INTO app.glossary_imports (
    source_name,
    source_version,
    idempotency_key,
    status,
    imported_by
  )
  VALUES (
    btrim(source_name),
    btrim(source_version),
    btrim(idempotency_key),
    'pending_approval'::app.glossary_import_status,
    caller_user_id
  )
  RETURNING id INTO new_import_id;

  FOR entry_rec IN
    SELECT value AS elem
    FROM jsonb_array_elements(payload -> 'entries') AS entries(value)
  LOOP
    entry_elem := entry_rec.elem;
    IF COALESCE(entry_elem ->> 'entry_type', '') = 'identifier_rule'
       AND app.glossary_identifier_rule_rejected(entry_elem ->> 'identifier_pattern') THEN
      RAISE EXCEPTION 'high_collision_rule';
    END IF;

    canonical_norm := search.normalize_arabic_v1(entry_elem ->> 'canonical_term');
    IF canonical_norm IS NULL OR canonical_norm = '' THEN
      RAISE EXCEPTION 'empty_canonical';
    END IF;

    INSERT INTO app.glossary_entries (
      import_id,
      entry_key,
      canonical_term,
      language,
      entry_type,
      effective_scope,
      identifier_pattern,
      checksum_algorithm
    )
    VALUES (
      new_import_id,
      entry_elem ->> 'entry_key',
      entry_elem ->> 'canonical_term',
      entry_elem ->> 'language',
      (entry_elem ->> 'entry_type')::app.glossary_entry_type,
      entry_elem ->> 'effective_scope',
      NULLIF(entry_elem ->> 'identifier_pattern', ''),
      NULLIF(entry_elem ->> 'checksum_algorithm', '')
    )
    RETURNING id INTO new_entry_id;

    new_entry_count := new_entry_count + 1;

    FOR alias_rec IN
      SELECT value AS elem
      FROM jsonb_array_elements(COALESCE(entry_elem -> 'aliases', '[]'::jsonb))
        AS aliases(value)
    LOOP
      alias_elem := alias_rec.elem;
      alias_norm := search.normalize_arabic_v1(alias_elem ->> 'alias');
      IF alias_norm IS NULL OR alias_norm = '' THEN
        RAISE EXCEPTION 'empty_alias';
      END IF;
      IF alias_norm = canonical_norm THEN
        RAISE EXCEPTION 'alias_equals_canonical';
      END IF;
      IF EXISTS (
        SELECT 1
        FROM app.glossary_aliases AS ga
        JOIN app.glossary_entries AS ge ON ge.id = ga.entry_id
        WHERE ga.alias_normalized = alias_norm
          AND ge.term_normalized IS DISTINCT FROM canonical_norm
          AND ge.effective_scope = (entry_elem ->> 'effective_scope')
      ) THEN
        RAISE EXCEPTION 'alias_conflict';
      END IF;
      IF EXISTS (
        SELECT 1
        FROM app.glossary_aliases AS ga
        JOIN app.glossary_entries AS ge ON ge.id = ga.entry_id
        WHERE ga.alias_normalized = alias_norm
          AND ge.term_normalized IS DISTINCT FROM canonical_norm
          AND ge.effective_scope IS DISTINCT FROM (entry_elem ->> 'effective_scope')
      ) THEN
        RAISE EXCEPTION 'cross_scope_conflict';
      END IF;
      INSERT INTO app.glossary_aliases (entry_id, alias, language)
      VALUES (
        new_entry_id,
        alias_elem ->> 'alias',
        alias_elem ->> 'language'
      );
      new_alias_count := new_alias_count + 1;
    END LOOP;
  END LOOP;

  UPDATE app.glossary_imports
  SET entry_count = new_entry_count,
      alias_count = new_alias_count
  WHERE id = new_import_id;

  PERFORM app.append_audit_event(
    'glossary_import_created',
    caller_user_id,
    profile_row.role,
    'glossary_import',
    new_import_id,
    caller_authorization_version,
    jsonb_build_object(
      'entry_count', new_entry_count,
      'alias_count', new_alias_count,
      'source_version', btrim(source_version)
    ),
    'glossary_import',
    'glossary_import',
    new_import_id,
    NULL
  );

  import_id := new_import_id;
  status := 'pending_approval'::app.glossary_import_status;
  entry_count := new_entry_count;
  alias_count := new_alias_count;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.import_glossary_batch(
  uuid, text, bigint, text, text, text, jsonb
) IS
  'Owner/admin glossary import. Pending rows do not populate search_aliases.';

CREATE OR REPLACE FUNCTION app.approve_glossary_import(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  target_import_id uuid
)
RETURNS TABLE (
  import_id uuid,
  status app.glossary_import_status,
  entry_count integer,
  alias_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  import_row app.glossary_imports%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  SELECT * INTO profile_row
  FROM app.profiles AS p
  WHERE p.user_id = caller_user_id;

  IF NOT FOUND OR profile_row.role NOT IN (
    'owner'::app.user_role, 'admin'::app.user_role
  ) THEN
    RAISE EXCEPTION 'forbidden';
  END IF;

  SELECT * INTO import_row
  FROM app.glossary_imports AS gi
  WHERE gi.id = target_import_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'import_not_found';
  END IF;

  IF import_row.status = 'approved'::app.glossary_import_status THEN
    RAISE EXCEPTION 'already_approved';
  END IF;

  IF import_row.status IS DISTINCT FROM 'pending_approval'::app.glossary_import_status THEN
    RAISE EXCEPTION 'unapproved_import';
  END IF;

  INSERT INTO app.search_aliases (
    alias,
    canonical_term,
    glossary_entry_id,
    import_id,
    language,
    effective_scope
  )
  SELECT
    ga.alias,
    ge.canonical_term,
    ge.id,
    ge.import_id,
    ga.language,
    ge.effective_scope
  FROM app.glossary_aliases AS ga
  JOIN app.glossary_entries AS ge ON ge.id = ga.entry_id
  WHERE ge.import_id = target_import_id;

  UPDATE app.glossary_imports AS gi
  SET status = 'approved'::app.glossary_import_status,
      approved_by = caller_user_id,
      approved_at = timezone('utc', now())
  WHERE gi.id = target_import_id
  RETURNING gi.* INTO import_row;

  PERFORM app.append_audit_event(
    'glossary_import_approved',
    caller_user_id,
    profile_row.role,
    'glossary_import',
    target_import_id,
    caller_authorization_version,
    jsonb_build_object(
      'entry_count', import_row.entry_count,
      'alias_count', import_row.alias_count
    ),
    'glossary_approve',
    'glossary_import',
    target_import_id,
    NULL
  );

  import_id := import_row.id;
  status := import_row.status;
  entry_count := import_row.entry_count;
  alias_count := import_row.alias_count;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.approve_glossary_import(uuid, text, bigint, uuid) IS
  'Projects approved glossary aliases into search_aliases.';

CREATE OR REPLACE FUNCTION app.rollback_glossary_import(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  target_import_id uuid
)
RETURNS TABLE (
  import_id uuid,
  status app.glossary_import_status,
  entry_count integer,
  alias_count integer
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  import_row app.glossary_imports%ROWTYPE;
BEGIN
  IF NOT app.validate_caller_context(
    caller_user_id, caller_role, caller_authorization_version
  ) THEN
    RAISE EXCEPTION 'authorization context rejected';
  END IF;

  SELECT * INTO profile_row
  FROM app.profiles AS p
  WHERE p.user_id = caller_user_id;

  IF NOT FOUND OR profile_row.role NOT IN (
    'owner'::app.user_role, 'admin'::app.user_role
  ) THEN
    RAISE EXCEPTION 'forbidden';
  END IF;

  SELECT * INTO import_row
  FROM app.glossary_imports AS gi
  WHERE gi.id = target_import_id
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'import_not_found';
  END IF;

  IF import_row.status = 'rolled_back'::app.glossary_import_status THEN
    RAISE EXCEPTION 'already_rolled_back';
  END IF;

  DELETE FROM app.search_aliases AS sa
  WHERE sa.import_id = target_import_id;

  UPDATE app.glossary_imports AS gi
  SET status = 'rolled_back'::app.glossary_import_status,
      rolled_back_by = caller_user_id,
      rolled_back_at = timezone('utc', now())
  WHERE gi.id = target_import_id
  RETURNING gi.* INTO import_row;

  PERFORM app.append_audit_event(
    'glossary_import_rolled_back',
    caller_user_id,
    profile_row.role,
    'glossary_import',
    target_import_id,
    caller_authorization_version,
    jsonb_build_object(
      'entry_count', import_row.entry_count,
      'alias_count', import_row.alias_count
    ),
    'glossary_rollback',
    'glossary_import',
    target_import_id,
    NULL
  );

  import_id := import_row.id;
  status := import_row.status;
  entry_count := import_row.entry_count;
  alias_count := import_row.alias_count;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.rollback_glossary_import(uuid, text, bigint, uuid) IS
  'Deletes the search_aliases projection for one glossary import.';

REVOKE ALL ON FUNCTION app.import_glossary_batch(
  uuid, text, bigint, text, text, text, jsonb
) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.approve_glossary_import(uuid, text, bigint, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.rollback_glossary_import(uuid, text, bigint, uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.glossary_payload_has_cycle(jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.glossary_identifier_rule_rejected(text) FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.import_glossary_batch(
  uuid, text, bigint, text, text, text, jsonb
) TO app_api;
GRANT EXECUTE ON FUNCTION app.approve_glossary_import(uuid, text, bigint, uuid) TO app_api;
GRANT EXECUTE ON FUNCTION app.rollback_glossary_import(uuid, text, bigint, uuid) TO app_api;
