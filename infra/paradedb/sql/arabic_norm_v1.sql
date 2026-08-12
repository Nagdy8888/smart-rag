-- ParadeDB bootstrap/qualification: arabic_norm_v1 search form (search schema).
-- Byte-identical twin of supabase/migrations pgvector gate migration and core Python.

CREATE SCHEMA IF NOT EXISTS search;

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
  v := regexp_replace(v, E'[\u064B-\u065F\u0670\u0640\u06D6-\u06ED]', '', 'g');
  v := translate(
    v,
    'أإآٱؤئىة٠١٢٣٤٥٦٧٨٩',
    'ااااوييه0123456789'
  );
  v := lower(v);
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

CREATE OR REPLACE FUNCTION search.assert_arabic_normalization_version(
  expected text DEFAULT 'arabic_norm_v1'
)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, search
AS $fn$
DECLARE
  active text;
BEGIN
  active := coalesce(
    nullif(current_setting('app.bm25_normalization_version', true), ''),
    search.arabic_normalization_version()
  );
  IF active IS DISTINCT FROM expected THEN
    RAISE EXCEPTION
      'BM25 normalization version mismatch: expected %, active %',
      expected,
      active;
  END IF;
END;
$fn$;

COMMENT ON FUNCTION search.assert_arabic_normalization_version(text) IS
  'Fail closed when ParadeDB query normalization version disagrees with canonical.';
