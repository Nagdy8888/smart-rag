-- Phase 2 Packet 6: pin the remaining advisor-reported function search path.

CREATE OR REPLACE FUNCTION search.arabic_normalization_version()
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog
AS $fn$
  SELECT 'arabic_norm_v1'::text;
$fn$;

COMMENT ON FUNCTION search.arabic_normalization_version() IS
  'Returns the immutable Arabic normalization contract version with a pinned search path.';
