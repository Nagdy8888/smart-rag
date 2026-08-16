-- Phase 5 Packet 6: expand graph_entity_rules, extraction policy, invalidation.
-- Expand-only. Do not DROP TABLE or COLUMN. Dual-write jsonb for Packet 4.

DO $$
BEGIN
  CREATE TYPE app.graph_entity_rule_status AS ENUM (
    'suggested',
    'approved',
    'revoked'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  CREATE TYPE app.graph_entity_rule_source AS ENUM (
    'admin',
    'feedback',
    'model'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  CREATE TYPE app.graph_relation_label_policy AS ENUM (
    'directed',
    'symmetric'
  );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

ALTER TABLE app.graph_entity_rules
  ADD COLUMN IF NOT EXISTS status app.graph_entity_rule_status,
  ADD COLUMN IF NOT EXISTS canonical_name text,
  ADD COLUMN IF NOT EXISTS display_label text,
  ADD COLUMN IF NOT EXISTS aliases text[] NOT NULL DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS do_not_merge text[] NOT NULL DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS languages text[] NOT NULL DEFAULT '{}'::text[],
  ADD COLUMN IF NOT EXISTS alias_scope text NOT NULL DEFAULT 'company',
  ADD COLUMN IF NOT EXISTS effective_from timestamptz,
  ADD COLUMN IF NOT EXISTS effective_until timestamptz,
  ADD COLUMN IF NOT EXISTS relation_label_policy app.graph_relation_label_policy
    NOT NULL DEFAULT 'directed',
  ADD COLUMN IF NOT EXISTS row_version bigint NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS reason text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS source app.graph_entity_rule_source NOT NULL DEFAULT 'admin',
  ADD COLUMN IF NOT EXISTS confidence numeric(5, 4),
  ADD COLUMN IF NOT EXISTS provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS created_by uuid REFERENCES app.profiles (user_id),
  ADD COLUMN IF NOT EXISTS approved_by uuid REFERENCES app.profiles (user_id),
  ADD COLUMN IF NOT EXISTS approved_at timestamptz,
  ADD COLUMN IF NOT EXISTS revoked_by uuid REFERENCES app.profiles (user_id),
  ADD COLUMN IF NOT EXISTS revoked_at timestamptz;

UPDATE app.graph_entity_rules
SET status = CASE
  WHEN active IS TRUE THEN 'approved'::app.graph_entity_rule_status
  ELSE 'revoked'::app.graph_entity_rule_status
END
WHERE status IS NULL;

ALTER TABLE app.graph_entity_rules
  ALTER COLUMN status SET DEFAULT 'suggested',
  ALTER COLUMN status SET NOT NULL;

UPDATE app.graph_entity_rules AS ger
SET
  canonical_name = COALESCE(ger.canonical_name, ger.rule ->> 'canonical_name'),
  aliases = CASE
    WHEN COALESCE(cardinality(ger.aliases), 0) > 0 THEN ger.aliases
    ELSE COALESCE(
      ARRAY(
        SELECT jsonb_array_elements_text(ger.rule -> 'aliases')
      ),
      '{}'::text[]
    )
  END,
  do_not_merge = CASE
    WHEN COALESCE(cardinality(ger.do_not_merge), 0) > 0 THEN ger.do_not_merge
    ELSE COALESCE(
      ARRAY(
        SELECT jsonb_array_elements_text(ger.rule -> 'do_not_merge')
      ),
      '{}'::text[]
    )
  END
WHERE ger.rule <> '{}'::jsonb;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_alias_scope_chk
      CHECK (alias_scope IN ('company', 'synthetic_eval'));
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_row_version_positive
      CHECK (row_version >= 1);
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_alias_limit
      CHECK (cardinality(aliases) <= 32 AND cardinality(do_not_merge) <= 32);
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_confidence_range
      CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1));
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_active_matches_status
      CHECK (
        (active IS TRUE AND status = 'approved')
        OR (active IS FALSE AND status <> 'approved')
      );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_effective_window
      CHECK (
        effective_from IS NULL
        OR effective_until IS NULL
        OR effective_until > effective_from
      );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

DO $$
BEGIN
  ALTER TABLE app.graph_entity_rules
    ADD CONSTRAINT graph_entity_rules_no_auto_approve
      CHECK (
        source = 'admin'::app.graph_entity_rule_source
        OR status <> 'approved'::app.graph_entity_rule_status
        OR approved_by IS NOT NULL
      );
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$$;

CREATE UNIQUE INDEX IF NOT EXISTS graph_entity_rules_approved_canonical_uq
  ON app.graph_entity_rules (
    entity_type,
    search.normalize_arabic_v1(canonical_name)
  )
  WHERE status = 'approved'::app.graph_entity_rule_status
    AND canonical_name IS NOT NULL
    AND btrim(canonical_name) <> '';

CREATE INDEX IF NOT EXISTS graph_entity_rules_status_idx
  ON app.graph_entity_rules (status, entity_type);

CREATE TABLE IF NOT EXISTS app.graph_extraction_policy (
  id uuid PRIMARY KEY,
  entity_rules_generation bigint NOT NULL DEFAULT 1,
  extraction_policy_hash text NOT NULL,
  allowed_entity_types text[] NOT NULL,
  allowed_languages text[] NOT NULL,
  entity_extract_max_gleaning integer NOT NULL DEFAULT 0,
  json_mode boolean NOT NULL DEFAULT true,
  relation_label_policy app.graph_relation_label_policy NOT NULL DEFAULT 'directed',
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_extraction_policy_singleton
    CHECK (id = '00000000-0000-0000-0000-000000000001'::uuid),
  CONSTRAINT graph_extraction_policy_generation_positive
    CHECK (entity_rules_generation >= 1),
  CONSTRAINT graph_extraction_policy_gleaning_bounds
    CHECK (entity_extract_max_gleaning >= 0 AND entity_extract_max_gleaning <= 3),
  CONSTRAINT graph_extraction_policy_hash_nonempty
    CHECK (btrim(extraction_policy_hash) <> ''),
  CONSTRAINT graph_extraction_policy_types_nonempty
    CHECK (cardinality(allowed_entity_types) >= 1),
  CONSTRAINT graph_extraction_policy_languages_nonempty
    CHECK (cardinality(allowed_languages) >= 1)
);

INSERT INTO app.graph_extraction_policy (
  id,
  entity_rules_generation,
  extraction_policy_hash,
  allowed_entity_types,
  allowed_languages,
  entity_extract_max_gleaning,
  json_mode,
  relation_label_policy
)
VALUES (
  '00000000-0000-0000-0000-000000000001'::uuid,
  1,
  'b8719e2481b2f8ed85be76d13e19c092428e92ffdf3d36bcd5e5e9656c65bd08',
  ARRAY[
    'CONCEPT',
    'EVENT',
    'LOCATION',
    'ORG',
    'ORGANIZATION',
    'PERSON',
    'PRODUCT',
    'PROJECT'
  ]::text[],
  ARRAY['ar', 'en', 'mixed']::text[],
  0,
  true,
  'directed'::app.graph_relation_label_policy
)
ON CONFLICT (id) DO NOTHING;

COMMENT ON TABLE app.graph_extraction_policy IS
  'Singleton extraction overlay. graph_pipeline_v1 is not rewritten; entity_rules_generation bumps instead.';
COMMENT ON TABLE app.graph_entity_rules IS
  'Owner/admin entity curation. Suggested/revoked rows never affect mapping. jsonb dual-written from typed columns.';
COMMENT ON COLUMN app.graph_entity_rules.row_version IS
  'Optimistic concurrency token. Stale updates fail closed.';
COMMENT ON COLUMN app.graph_extraction_policy.entity_rules_generation IS
  'Monotonic approved-rule generation included in mapping config after the first bump.';

CREATE OR REPLACE FUNCTION app.sync_graph_entity_rule_row()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app, search
AS $fn$
BEGIN
  IF NEW.canonical_name IS NULL AND NEW.rule ? 'canonical_name' THEN
    NEW.canonical_name := NULLIF(btrim(NEW.rule ->> 'canonical_name'), '');
  END IF;
  IF COALESCE(cardinality(NEW.aliases), 0) = 0 AND NEW.rule ? 'aliases' THEN
    NEW.aliases := COALESCE(
      ARRAY(SELECT jsonb_array_elements_text(NEW.rule -> 'aliases')),
      '{}'::text[]
    );
  END IF;
  IF COALESCE(cardinality(NEW.do_not_merge), 0) = 0 AND NEW.rule ? 'do_not_merge' THEN
    NEW.do_not_merge := COALESCE(
      ARRAY(SELECT jsonb_array_elements_text(NEW.rule -> 'do_not_merge')),
      '{}'::text[]
    );
  END IF;
  NEW.active := (NEW.status = 'approved'::app.graph_entity_rule_status);
  NEW.rule := jsonb_strip_nulls(
    jsonb_build_object(
      'canonical_name', NEW.canonical_name,
      'aliases', to_jsonb(NEW.aliases),
      'do_not_merge', to_jsonb(NEW.do_not_merge),
      'display_label', NEW.display_label,
      'languages', to_jsonb(NEW.languages),
      'relation_label_policy', NEW.relation_label_policy::text,
      'status', NEW.status::text,
      'source', NEW.source::text
    )
  );
  RETURN NEW;
END;
$fn$;

DROP TRIGGER IF EXISTS graph_entity_rules_sync_row ON app.graph_entity_rules;
CREATE TRIGGER graph_entity_rules_sync_row
  BEFORE INSERT OR UPDATE ON app.graph_entity_rules
  FOR EACH ROW
  EXECUTE FUNCTION app.sync_graph_entity_rule_row();

CREATE OR REPLACE FUNCTION app.apply_entity_rule_graph_invalidation(p_reason text)
RETURNS TABLE (
  entity_rules_generation bigint,
  rebuild_job_id uuid,
  repair_job_id uuid
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  v_generation bigint;
  v_hash text;
  v_workspace text := 'company_default';
  v_rebuild_key text;
  v_reason text := left(COALESCE(NULLIF(btrim(p_reason), ''), 'entity_rules_changed'), 512);
  v_rebuild uuid;
  v_repair uuid;
  v_idem text;
  v_snapshot jsonb;
BEGIN
  SELECT COALESCE(ws.workspace_key, 'company_default')
  INTO v_workspace
  FROM app.graph_active_workspace_pointer AS pointer
  LEFT JOIN app.graph_workspaces AS ws ON ws.id = pointer.workspace_id
  WHERE pointer.id = '00000000-0000-0000-0000-000000000001'::uuid;

  v_workspace := COALESCE(NULLIF(btrim(v_workspace), ''), 'company_default');
  v_rebuild_key := v_workspace || '__rebuild';

  UPDATE app.graph_extraction_policy AS pol
  SET
    entity_rules_generation = pol.entity_rules_generation + 1,
    updated_at = timezone('utc', now())
  WHERE pol.id = '00000000-0000-0000-0000-000000000001'::uuid
  RETURNING
    pol.entity_rules_generation,
    pol.extraction_policy_hash
  INTO v_generation, v_hash;

  UPDATE app.lightrag_source_map
  SET
    config_generation = 'invalidated:' || left(config_generation, 200),
    mapped_at = timezone('utc', now())
  WHERE workspace_key = v_workspace
    AND config_generation IS NOT NULL
    AND btrim(config_generation) <> ''
    AND config_generation NOT LIKE 'invalidated:%';

  UPDATE app.lightrag_chunk_map
  SET
    config_generation = 'invalidated:' || left(config_generation, 200),
    mapped_at = timezone('utc', now())
  WHERE workspace_key = v_workspace
    AND config_generation IS NOT NULL
    AND btrim(config_generation) <> ''
    AND config_generation NOT LIKE 'invalidated:%';

  UPDATE app.graph_evidence_map
  SET
    config_generation = 'invalidated:' || left(config_generation, 200),
    mapped_at = timezone('utc', now())
  WHERE workspace_key = v_workspace
    AND config_generation IS NOT NULL
    AND btrim(config_generation) <> ''
    AND config_generation NOT LIKE 'invalidated:%';

  UPDATE app.document_versions
  SET
    status = 'graph_pending'::app.document_status,
    updated_at = timezone('utc', now())
  WHERE status = 'graph_ready'::app.document_status;

  v_snapshot := jsonb_build_object(
    'entity_rules_generation', v_generation,
    'extraction_policy_hash', v_hash,
    'graph_pipeline_version', 'graph_pipeline_v1',
    'live_pointer_unchanged', true
  );

  INSERT INTO app.graph_workspaces (workspace_key, state, config_snapshot)
  VALUES (
    v_rebuild_key,
    'building'::app.graph_workspace_state,
    v_snapshot
  )
  ON CONFLICT (workspace_key) DO UPDATE
  SET
    config_snapshot = app.graph_workspaces.config_snapshot || EXCLUDED.config_snapshot,
    updated_at = timezone('utc', now())
  WHERE app.graph_workspaces.state IS DISTINCT FROM 'retired'::app.graph_workspace_state;

  INSERT INTO app.graph_map_repair_jobs (
    workspace_key, graph_object_type, graph_object_id, map_kind,
    config_generation, reason
  )
  VALUES (
    v_workspace,
    'policy',
    'entity_rules',
    'map_repair',
    'invalidated:' || v_generation::text,
    v_reason
  )
  ON CONFLICT (
    workspace_key, graph_object_type, graph_object_id, map_kind, config_generation
  ) DO UPDATE SET
    reason = EXCLUDED.reason,
    status = 'pending'::app.job_status,
    updated_at = timezone('utc', now())
  RETURNING id INTO v_repair;

  v_idem := format('graph_entity_rules_rebuild:%s:%s', v_workspace, v_generation);
  INSERT INTO app.lightrag_index_jobs (
    operation,
    priority,
    idempotency_key,
    payload_ref
  )
  VALUES (
    'rebuild'::app.lightrag_job_operation,
    'normal'::app.job_priority,
    v_idem,
    jsonb_build_object(
      'reason', v_reason,
      'workspace_key', v_workspace,
      'rebuild_workspace_key', v_rebuild_key,
      'entity_rules_generation', v_generation,
      'isolate_only', true,
      'live_pointer_unchanged', true,
      'graph_pipeline_version', 'graph_pipeline_v1'
    )
  )
  ON CONFLICT (idempotency_key) DO NOTHING
  RETURNING id INTO v_rebuild;

  IF v_rebuild IS NULL THEN
    SELECT j.id INTO v_rebuild
    FROM app.lightrag_index_jobs AS j
    WHERE j.idempotency_key = v_idem;
  END IF;

  entity_rules_generation := v_generation;
  rebuild_job_id := v_rebuild;
  repair_job_id := v_repair;
  RETURN NEXT;
END;
$fn$;

COMMENT ON FUNCTION app.apply_entity_rule_graph_invalidation(text) IS
  'Stamp application maps stale, mark versions not Graph Ready, enqueue isolated rebuild. Pointer unchanged. No vendor-graph DML.';

CREATE OR REPLACE FUNCTION app.graph_entity_rule_has_conflict(
  p_rule_id uuid,
  p_entity_type text,
  p_canonical text,
  p_aliases text[],
  p_do_not_merge text[]
)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  canonical_norm text;
  alias_norm text;
  other record;
  names text[];
  alias_names text[];
BEGIN
  canonical_norm := search.normalize_arabic_v1(p_canonical);
  alias_names := ARRAY(
    SELECT search.normalize_arabic_v1(a)
    FROM unnest(COALESCE(p_aliases, '{}'::text[])) AS a
    WHERE btrim(a) <> ''
      AND search.normalize_arabic_v1(a) IS DISTINCT FROM canonical_norm
  );
  IF EXISTS (
    SELECT 1
    FROM unnest(alias_names) AS n
    GROUP BY n
    HAVING count(*) > 1
  ) THEN
    RETURN 'duplicate_alias';
  END IF;
  names := ARRAY[canonical_norm] || alias_names;
  IF EXISTS (
    SELECT 1
    FROM unnest(COALESCE(p_do_not_merge, '{}'::text[])) AS blocked
    WHERE search.normalize_arabic_v1(blocked) = ANY (names)
  ) THEN
    RETURN 'do_not_merge_conflict';
  END IF;
  FOR other IN
    SELECT
      ger.id,
      ger.canonical_name,
      ger.aliases,
      ger.do_not_merge
    FROM app.graph_entity_rules AS ger
    WHERE ger.status = 'approved'::app.graph_entity_rule_status
      AND ger.entity_type = p_entity_type
      AND (p_rule_id IS NULL OR ger.id <> p_rule_id)
  LOOP
    IF EXISTS (
      SELECT 1
      FROM unnest(COALESCE(other.do_not_merge, '{}'::text[])) AS blocked
      WHERE search.normalize_arabic_v1(blocked) = ANY (names)
    ) THEN
      RETURN 'do_not_merge_conflict';
    END IF;
    IF EXISTS (
      SELECT 1
      FROM unnest(names) AS n
      WHERE n = search.normalize_arabic_v1(other.canonical_name)
         OR n IN (
           SELECT search.normalize_arabic_v1(a)
           FROM unnest(COALESCE(other.aliases, '{}'::text[])) AS a
         )
    ) THEN
      RETURN 'alias_conflict';
    END IF;
  END LOOP;
  WITH RECURSIVE edges AS (
    SELECT
      search.normalize_arabic_v1(alias_elem) AS src,
      canonical_norm AS dst
    FROM unnest(COALESCE(p_aliases, '{}'::text[])) AS alias_elem
    WHERE btrim(alias_elem) <> ''
      AND search.normalize_arabic_v1(alias_elem) IS DISTINCT FROM canonical_norm
    UNION ALL
    SELECT
      search.normalize_arabic_v1(alias_elem) AS src,
      search.normalize_arabic_v1(ger.canonical_name) AS dst
    FROM app.graph_entity_rules AS ger
    CROSS JOIN LATERAL unnest(COALESCE(ger.aliases, '{}'::text[])) AS alias_elem
    WHERE ger.status = 'approved'::app.graph_entity_rule_status
      AND ger.entity_type = p_entity_type
      AND (p_rule_id IS NULL OR ger.id <> p_rule_id)
      AND btrim(alias_elem) <> ''
      AND search.normalize_arabic_v1(alias_elem)
        IS DISTINCT FROM search.normalize_arabic_v1(ger.canonical_name)
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
  SELECT 'alias_cycle'
  INTO alias_norm
  FROM walk
  JOIN edges ON edges.src = walk.dst AND edges.dst = ANY (walk.seen)
  LIMIT 1;
  IF alias_norm IS NOT NULL THEN
    RETURN 'alias_cycle';
  END IF;
  RETURN NULL;
END;
$fn$;

CREATE OR REPLACE FUNCTION app._graph_entity_rule_require_admin(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS app.profiles
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
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
    RAISE EXCEPTION 'forbidden';
  END IF;
  IF profile_row.role NOT IN ('owner'::app.user_role, 'admin'::app.user_role) THEN
    RAISE EXCEPTION 'forbidden';
  END IF;
  RETURN profile_row;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.upsert_graph_entity_rule(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_rule_id uuid,
  p_row_version bigint,
  p_payload jsonb
)
RETURNS TABLE (
  rule_id uuid,
  status app.graph_entity_rule_status,
  row_version bigint,
  entity_rules_generation bigint,
  rebuild_job_id uuid,
  repair_job_id uuid,
  invalidated boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  payload jsonb := COALESCE(p_payload, '{}'::jsonb);
  v_type text;
  v_canonical text;
  v_status app.graph_entity_rule_status;
  v_source app.graph_entity_rule_source;
  v_aliases text[];
  v_blocked text[];
  v_conflict text;
  v_row app.graph_entity_rules%ROWTYPE;
  v_was_approved boolean := false;
  v_generation bigint := 1;
  v_rebuild uuid;
  v_repair uuid;
BEGIN
  profile_row := app._graph_entity_rule_require_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  v_type := upper(btrim(COALESCE(payload ->> 'entity_type', '')));
  v_canonical := NULLIF(btrim(COALESCE(payload ->> 'canonical_name', '')), '');
  v_source := COALESCE(
    (payload ->> 'source')::app.graph_entity_rule_source,
    'admin'::app.graph_entity_rule_source
  );
  v_status := COALESCE(
    (payload ->> 'status')::app.graph_entity_rule_status,
    CASE
      WHEN v_source = 'admin'::app.graph_entity_rule_source THEN
        'approved'::app.graph_entity_rule_status
      ELSE 'suggested'::app.graph_entity_rule_status
    END
  );
  IF v_source IN (
    'feedback'::app.graph_entity_rule_source,
    'model'::app.graph_entity_rule_source
  ) AND v_status = 'approved'::app.graph_entity_rule_status THEN
    RAISE EXCEPTION 'auto_approval_forbidden';
  END IF;
  IF v_canonical IS NULL THEN
    RAISE EXCEPTION 'canonical_name_required';
  END IF;
  IF NOT EXISTS (
    SELECT 1
    FROM app.graph_extraction_policy AS pol
    CROSS JOIN LATERAL unnest(pol.allowed_entity_types) AS allowed(entity_type)
    WHERE pol.id = '00000000-0000-0000-0000-000000000001'::uuid
      AND allowed.entity_type = v_type
  ) THEN
    RAISE EXCEPTION 'unknown_entity_type';
  END IF;
  IF COALESCE(payload ->> 'alias_scope', 'company') NOT IN ('company', 'synthetic_eval') THEN
    RAISE EXCEPTION 'invalid_alias_scope';
  END IF;
  v_aliases := COALESCE(
    ARRAY(SELECT jsonb_array_elements_text(payload -> 'aliases')),
    '{}'::text[]
  );
  v_blocked := COALESCE(
    ARRAY(SELECT jsonb_array_elements_text(payload -> 'do_not_merge')),
    '{}'::text[]
  );
  IF EXISTS (
    SELECT 1
    FROM unnest(v_aliases || v_blocked || ARRAY[v_canonical]) AS token
    WHERE token LIKE '%::%'
      AND split_part(token, '::', 1) <> ''
      AND upper(split_part(token, '::', 1)) IS DISTINCT FROM v_type
  ) THEN
    RAISE EXCEPTION 'cross_type_alias';
  END IF;
  IF p_rule_id IS NOT NULL THEN
    SELECT * INTO v_row
    FROM app.graph_entity_rules AS ger
    WHERE ger.id = p_rule_id
    FOR UPDATE;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'rule_not_found';
    END IF;
    IF p_row_version IS NULL OR v_row.row_version IS DISTINCT FROM p_row_version THEN
      RAISE EXCEPTION 'stale_row_version';
    END IF;
    v_was_approved := (v_row.status = 'approved'::app.graph_entity_rule_status);
  END IF;
  IF v_status = 'approved'::app.graph_entity_rule_status THEN
    v_conflict := app.graph_entity_rule_has_conflict(
      p_rule_id, v_type, v_canonical, v_aliases, v_blocked
    );
    IF v_conflict IS NOT NULL THEN
      RAISE EXCEPTION '%', v_conflict;
    END IF;
  END IF;
  IF p_rule_id IS NULL THEN
    INSERT INTO app.graph_entity_rules (
      entity_type,
      canonical_name,
      display_label,
      aliases,
      do_not_merge,
      languages,
      alias_scope,
      relation_label_policy,
      reason,
      source,
      confidence,
      provenance,
      status,
      created_by,
      approved_by,
      approved_at
    )
    VALUES (
      v_type,
      v_canonical,
      NULLIF(btrim(COALESCE(payload ->> 'display_label', '')), ''),
      v_aliases,
      v_blocked,
      COALESCE(
        ARRAY(SELECT jsonb_array_elements_text(payload -> 'languages')),
        '{}'::text[]
      ),
      COALESCE(payload ->> 'alias_scope', 'company'),
      COALESCE(
        (payload ->> 'relation_label_policy')::app.graph_relation_label_policy,
        'directed'::app.graph_relation_label_policy
      ),
      left(COALESCE(payload ->> 'reason', ''), 512),
      v_source,
      NULLIF(payload ->> 'confidence', '')::numeric,
      COALESCE(payload -> 'provenance', '{}'::jsonb),
      v_status,
      caller_user_id,
      CASE
        WHEN v_status = 'approved'::app.graph_entity_rule_status THEN caller_user_id
        ELSE NULL
      END,
      CASE
        WHEN v_status = 'approved'::app.graph_entity_rule_status THEN timezone('utc', now())
        ELSE NULL
      END
    )
    RETURNING * INTO v_row;
  ELSE
    UPDATE app.graph_entity_rules AS ger
    SET
      entity_type = v_type,
      canonical_name = v_canonical,
      display_label = NULLIF(btrim(COALESCE(payload ->> 'display_label', '')), ''),
      aliases = v_aliases,
      do_not_merge = v_blocked,
      languages = COALESCE(
        ARRAY(SELECT jsonb_array_elements_text(payload -> 'languages')),
        ger.languages
      ),
      alias_scope = COALESCE(payload ->> 'alias_scope', ger.alias_scope),
      relation_label_policy = COALESCE(
        (payload ->> 'relation_label_policy')::app.graph_relation_label_policy,
        ger.relation_label_policy
      ),
      reason = left(COALESCE(payload ->> 'reason', ger.reason), 512),
      row_version = ger.row_version + 1,
      updated_at = timezone('utc', now())
    WHERE ger.id = p_rule_id
      AND ger.row_version = p_row_version
    RETURNING * INTO v_row;
    IF NOT FOUND THEN
      RAISE EXCEPTION 'stale_row_version';
    END IF;
  END IF;
  IF v_row.status = 'approved'::app.graph_entity_rule_status OR v_was_approved THEN
    SELECT
      inv.entity_rules_generation,
      inv.rebuild_job_id,
      inv.repair_job_id
    INTO v_generation, v_rebuild, v_repair
    FROM app.apply_entity_rule_graph_invalidation('entity_rule_upsert') AS inv;
  ELSE
    SELECT pol.entity_rules_generation INTO v_generation
    FROM app.graph_extraction_policy AS pol
    WHERE pol.id = '00000000-0000-0000-0000-000000000001'::uuid;
  END IF;
  PERFORM app.append_audit_event(
    'graph.entity_rules.upserted',
    caller_user_id,
    profile_row.role,
    'graph_entity_rule',
    v_row.id,
    caller_authorization_version,
    jsonb_build_object(
      'status', v_row.status::text,
      'entity_type', v_row.entity_type,
      'invalidated',
      (v_row.status = 'approved'::app.graph_entity_rule_status OR v_was_approved),
      'entity_rules_generation', v_generation
    )
  );
  rule_id := v_row.id;
  status := v_row.status;
  row_version := v_row.row_version;
  entity_rules_generation := COALESCE(v_generation, 1);
  rebuild_job_id := v_rebuild;
  repair_job_id := v_repair;
  invalidated := (v_row.status = 'approved'::app.graph_entity_rule_status OR v_was_approved);
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.approve_graph_entity_rule(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_rule_id uuid,
  p_row_version bigint,
  p_payload jsonb
)
RETURNS TABLE (
  rule_id uuid,
  status app.graph_entity_rule_status,
  row_version bigint,
  entity_rules_generation bigint,
  rebuild_job_id uuid,
  repair_job_id uuid,
  invalidated boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  v_row app.graph_entity_rules%ROWTYPE;
  v_conflict text;
  v_invalidation record;
BEGIN
  profile_row := app._graph_entity_rule_require_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  IF p_rule_id IS NULL OR p_row_version IS NULL THEN
    RAISE EXCEPTION 'stale_row_version';
  END IF;
  SELECT * INTO v_row
  FROM app.graph_entity_rules AS ger
  WHERE ger.id = p_rule_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'rule_not_found';
  END IF;
  IF v_row.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'stale_row_version';
  END IF;
  IF v_row.status = 'approved'::app.graph_entity_rule_status THEN
    RAISE EXCEPTION 'already_approved';
  END IF;
  IF v_row.status = 'revoked'::app.graph_entity_rule_status THEN
    RAISE EXCEPTION 'already_revoked';
  END IF;
  v_conflict := app.graph_entity_rule_has_conflict(
    v_row.id, v_row.entity_type, v_row.canonical_name, v_row.aliases, v_row.do_not_merge
  );
  IF v_conflict IS NOT NULL THEN
    RAISE EXCEPTION '%', v_conflict;
  END IF;
  UPDATE app.graph_entity_rules AS ger
  SET
    status = 'approved'::app.graph_entity_rule_status,
    approved_by = caller_user_id,
    approved_at = timezone('utc', now()),
    row_version = ger.row_version + 1
  WHERE ger.id = p_rule_id
    AND ger.row_version = p_row_version
  RETURNING * INTO v_row;
  SELECT * INTO v_invalidation
  FROM app.apply_entity_rule_graph_invalidation('entity_rule_approved');
  PERFORM app.append_audit_event(
    'graph.entity_rules.approved',
    caller_user_id,
    profile_row.role,
    'graph_entity_rule',
    v_row.id,
    caller_authorization_version,
    jsonb_build_object(
      'entity_type', v_row.entity_type,
      'source', v_row.source::text,
      'entity_rules_generation', v_invalidation.entity_rules_generation
    )
  );
  rule_id := v_row.id;
  status := v_row.status;
  row_version := v_row.row_version;
  entity_rules_generation := v_invalidation.entity_rules_generation;
  rebuild_job_id := v_invalidation.rebuild_job_id;
  repair_job_id := v_invalidation.repair_job_id;
  invalidated := true;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.revoke_graph_entity_rule(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint,
  p_rule_id uuid,
  p_row_version bigint,
  p_payload jsonb
)
RETURNS TABLE (
  rule_id uuid,
  status app.graph_entity_rule_status,
  row_version bigint,
  entity_rules_generation bigint,
  rebuild_job_id uuid,
  repair_job_id uuid,
  invalidated boolean
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, app, search
AS $fn$
DECLARE
  profile_row app.profiles%ROWTYPE;
  v_row app.graph_entity_rules%ROWTYPE;
  v_was_approved boolean;
  v_generation bigint := 1;
  v_rebuild uuid;
  v_repair uuid;
BEGIN
  profile_row := app._graph_entity_rule_require_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  IF p_rule_id IS NULL OR p_row_version IS NULL THEN
    RAISE EXCEPTION 'stale_row_version';
  END IF;
  SELECT * INTO v_row
  FROM app.graph_entity_rules AS ger
  WHERE ger.id = p_rule_id
  FOR UPDATE;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'rule_not_found';
  END IF;
  IF v_row.row_version IS DISTINCT FROM p_row_version THEN
    RAISE EXCEPTION 'stale_row_version';
  END IF;
  IF v_row.status = 'revoked'::app.graph_entity_rule_status THEN
    RAISE EXCEPTION 'already_revoked';
  END IF;
  v_was_approved := (v_row.status = 'approved'::app.graph_entity_rule_status);
  UPDATE app.graph_entity_rules AS ger
  SET
    status = 'revoked'::app.graph_entity_rule_status,
    revoked_by = caller_user_id,
    revoked_at = timezone('utc', now()),
    row_version = ger.row_version + 1
  WHERE ger.id = p_rule_id
    AND ger.row_version = p_row_version
  RETURNING * INTO v_row;
  IF v_was_approved THEN
    SELECT
      inv.entity_rules_generation,
      inv.rebuild_job_id,
      inv.repair_job_id
    INTO v_generation, v_rebuild, v_repair
    FROM app.apply_entity_rule_graph_invalidation('entity_rule_revoked') AS inv;
  ELSE
    SELECT pol.entity_rules_generation INTO v_generation
    FROM app.graph_extraction_policy AS pol
    WHERE pol.id = '00000000-0000-0000-0000-000000000001'::uuid;
  END IF;
  PERFORM app.append_audit_event(
    'graph.entity_rules.revoked',
    caller_user_id,
    profile_row.role,
    'graph_entity_rule',
    v_row.id,
    caller_authorization_version,
    jsonb_build_object(
      'was_approved', v_was_approved,
      'entity_type', v_row.entity_type,
      'entity_rules_generation', v_generation
    )
  );
  rule_id := v_row.id;
  status := v_row.status;
  row_version := v_row.row_version;
  entity_rules_generation := COALESCE(v_generation, 1);
  rebuild_job_id := v_rebuild;
  repair_job_id := v_repair;
  invalidated := v_was_approved;
  RETURN NEXT;
END;
$fn$;

CREATE OR REPLACE FUNCTION app.list_graph_entity_rules(
  caller_user_id uuid,
  caller_role text,
  caller_authorization_version bigint
)
RETURNS TABLE (
  id uuid,
  entity_type text,
  canonical_name text,
  display_label text,
  aliases text[],
  do_not_merge text[],
  languages text[],
  alias_scope text,
  relation_label_policy app.graph_relation_label_policy,
  status app.graph_entity_rule_status,
  active boolean,
  row_version bigint,
  source app.graph_entity_rule_source,
  reason text,
  confidence numeric,
  created_at timestamptz,
  updated_at timestamptz
)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  PERFORM app._graph_entity_rule_require_admin(
    caller_user_id, caller_role, caller_authorization_version
  );
  RETURN QUERY
  SELECT
    ger.id,
    ger.entity_type,
    ger.canonical_name,
    ger.display_label,
    ger.aliases,
    ger.do_not_merge,
    ger.languages,
    ger.alias_scope,
    ger.relation_label_policy,
    ger.status,
    ger.active,
    ger.row_version,
    ger.source,
    ger.reason,
    ger.confidence,
    ger.created_at,
    ger.updated_at
  FROM app.graph_entity_rules AS ger
  ORDER BY ger.updated_at DESC, ger.id;
END;
$fn$;

ALTER TABLE app.graph_entity_rules FORCE ROW LEVEL SECURITY;
ALTER TABLE app.graph_extraction_policy ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.graph_extraction_policy FORCE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_extraction_policy'
      AND policyname = 'graph_extraction_policy_worker_rw'
  ) THEN
    CREATE POLICY graph_extraction_policy_worker_rw
      ON app.graph_extraction_policy
      FOR ALL
      TO app_worker
      USING (true)
      WITH CHECK (true);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'app'
      AND tablename = 'graph_extraction_policy'
      AND policyname = 'graph_extraction_policy_api_select'
  ) THEN
    CREATE POLICY graph_extraction_policy_api_select
      ON app.graph_extraction_policy
      FOR SELECT
      TO app_api
      USING (true);
  END IF;
END
$$;

GRANT SELECT ON app.graph_extraction_policy TO app_api;
GRANT SELECT, UPDATE ON app.graph_extraction_policy TO app_worker;
GRANT SELECT, INSERT, UPDATE ON app.graph_entity_rules TO app_worker;

REVOKE ALL ON FUNCTION app.apply_entity_rule_graph_invalidation(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.graph_entity_rule_has_conflict(uuid, text, text, text[], text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION app._graph_entity_rule_require_admin(uuid, text, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.upsert_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.approve_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.revoke_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.list_graph_entity_rules(uuid, text, bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION app.sync_graph_entity_rule_row() FROM PUBLIC;

GRANT EXECUTE ON FUNCTION app.apply_entity_rule_graph_invalidation(text) TO app_worker;
GRANT EXECUTE ON FUNCTION app.upsert_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) TO app_api;
GRANT EXECUTE ON FUNCTION app.approve_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) TO app_api;
GRANT EXECUTE ON FUNCTION app.revoke_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) TO app_api;
GRANT EXECUTE ON FUNCTION app.list_graph_entity_rules(uuid, text, bigint) TO app_api;

COMMENT ON FUNCTION app.upsert_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) IS
  'Owner/admin create or update. Approved writes invalidate maps and schedule rebuild. Suggestions stay inactive.';
COMMENT ON FUNCTION app.approve_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) IS
  'Explicit owner/admin approval. Never auto-approves feedback/model rows.';
COMMENT ON FUNCTION app.revoke_graph_entity_rule(uuid, text, bigint, uuid, bigint, jsonb) IS
  'Revoke a rule. Approved revocations invalidate maps; suggestions do not.';
COMMENT ON FUNCTION app.list_graph_entity_rules(uuid, text, bigint) IS
  'Owner/admin listing including inactive suggestions. Members are forbidden.';

CREATE OR REPLACE FUNCTION app.reject_restricted_graph_index_job()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, app
AS $fn$
BEGIN
  IF COALESCE(NEW.payload_ref->>'reconciliation', '') = 'true' THEN
    RETURN NEW;
  END IF;
  IF NEW.operation = 'rebuild'::app.lightrag_job_operation
    AND NEW.document_id IS NULL
    AND COALESCE(NEW.payload_ref->>'isolate_only', '') = 'true'
  THEN
    RETURN NEW;
  END IF;
  IF NEW.operation IN ('index', 'rebuild') THEN
    PERFORM app.assert_graph_index_allowed(NEW.document_id, NEW.version_id);
  END IF;
  RETURN NEW;
END;
$fn$;

COMMENT ON FUNCTION app.reject_restricted_graph_index_job() IS
  'Reject restricted graph index/rebuild jobs. Reconciliation and isolated entity-rule rebuilds with no document_id skip the eligibility gate.';
