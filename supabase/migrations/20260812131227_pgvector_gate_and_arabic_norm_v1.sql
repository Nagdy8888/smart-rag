-- Phase 2 Packet 1: pgvector 0.8+ iterative-scan gate + arabic_norm_v1 only.
-- Do not install pg_search on Supabase. Full application schema is Packet 2+.

CREATE SCHEMA IF NOT EXISTS search;

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions;

CREATE OR REPLACE FUNCTION search.assert_pgvector_capabilities()
RETURNS text
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, extensions, search
AS $fn$
DECLARE
  ver text;
  major int;
  minor int;
BEGIN
  SELECT e.extversion INTO ver
  FROM pg_extension AS e
  WHERE e.extname = 'vector';

  IF ver IS NULL THEN
    RAISE EXCEPTION 'pgvector extension missing';
  END IF;

  major := split_part(ver, '.', 1)::integer;
  minor := split_part(ver, '.', 2)::integer;
  IF major < 0 OR (major = 0 AND minor < 8) THEN
    RAISE EXCEPTION 'pgvector % below required 0.8+', ver;
  END IF;

  PERFORM set_config('hnsw.iterative_scan', 'relaxed_order', true);
  IF current_setting('hnsw.iterative_scan', true) IS DISTINCT FROM 'relaxed_order' THEN
    RAISE EXCEPTION 'hnsw.iterative_scan rejected relaxed_order';
  END IF;
  PERFORM set_config('hnsw.iterative_scan', 'strict_order', true);
  PERFORM set_config('hnsw.iterative_scan', 'off', true);
  PERFORM set_config('hnsw.ef_search', '40', true);

  RETURN ver;
END;
$fn$;

COMMENT ON FUNCTION search.assert_pgvector_capabilities() IS
  'Fail closed when pgvector is below 0.8 or iterative-scan GUCs are unavailable.';

CREATE OR REPLACE FUNCTION search.normalize_arabic_v1(input text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $fn$
DECLARE
  v text;
BEGIN
  IF input IS NULL THEN
    RETURN NULL;
  END IF;
  IF input = '' THEN
    RETURN '';
  END IF;

  v := normalize(input, NFC);
  -- Harakat, superscript alef, tatweel, and Quranic annotation marks.
  v := regexp_replace(v, E'[\u064B-\u065F\u0670\u0640\u06D6-\u06ED]', '', 'g');
  v := translate(
    v,
    'أإآٱؤئىة٠١٢٣٤٥٦٧٨٩',
    'ااااوييه0123456789'
  );
  v := lower(v);
  -- Keep Arabic letters (not full Arabic block punctuation), Latin alnum, _, space, hyphen.
  v := regexp_replace(
    v,
    E'[^\u0621-\u063A\u0641-\u064A\u0660-\u0669\u0671-\u06D3\u06D5\u06EE\u06EF\u06FA-\u06FFa-zA-Z0-9_[:space:]-]+',
    ' ',
    'g'
  );
  v := regexp_replace(v, E'[[:space:]]+', ' ', 'g');
  RETURN btrim(v);
END;
$fn$;

COMMENT ON FUNCTION search.normalize_arabic_v1(text) IS
  'arabic_norm_v1 BM25 search form; never use for raw citation text or offsets.';

CREATE OR REPLACE FUNCTION search.arabic_normalization_version()
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $fn$
  SELECT 'arabic_norm_v1'::text;
$fn$;

DO $gate$
DECLARE
  installed text;
BEGIN
  installed := search.assert_pgvector_capabilities();
  RAISE NOTICE 'pgvector capability gate passed: %', installed;
END;
$gate$;

REVOKE ALL ON FUNCTION search.assert_pgvector_capabilities() FROM PUBLIC;
REVOKE ALL ON FUNCTION search.normalize_arabic_v1(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION search.arabic_normalization_version() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION search.assert_pgvector_capabilities() TO postgres, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION search.normalize_arabic_v1(text) TO postgres, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION search.arabic_normalization_version() TO postgres, anon, authenticated, service_role;
