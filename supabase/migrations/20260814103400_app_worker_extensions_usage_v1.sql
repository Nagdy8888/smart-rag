-- Phase 3 gap close-out: worker canonical writes need vector + Arabic normalizer.
GRANT USAGE ON SCHEMA extensions TO app_worker;
GRANT USAGE ON SCHEMA search TO app_worker;
GRANT EXECUTE ON FUNCTION search.normalize_arabic_v1(text) TO app_worker;
GRANT EXECUTE ON FUNCTION search.arabic_normalization_version() TO app_worker;

DROP POLICY IF EXISTS document_search_terms_worker_rw ON app.document_search_terms;
CREATE POLICY document_search_terms_worker_rw
  ON app.document_search_terms
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS document_tables_worker_rw ON app.document_tables;
CREATE POLICY document_tables_worker_rw
  ON app.document_tables
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS document_table_columns_worker_rw ON app.document_table_columns;
CREATE POLICY document_table_columns_worker_rw
  ON app.document_table_columns
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

DROP POLICY IF EXISTS search_aliases_worker_rw ON app.search_aliases;
CREATE POLICY search_aliases_worker_rw
  ON app.search_aliases
  FOR ALL
  TO app_worker
  USING (true)
  WITH CHECK (true);

COMMENT ON SCHEMA extensions IS
  'Supabase extensions schema; app_worker needs USAGE to write pgvector embeddings.';
