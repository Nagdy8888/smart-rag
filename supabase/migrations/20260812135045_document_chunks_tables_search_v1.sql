-- Phase 2 Packet 2: canonical chunks, typed tables, search terms, aliases.

CREATE TABLE app.document_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  chunk_index integer NOT NULL,
  raw_text text NOT NULL,
  search_normalized text GENERATED ALWAYS AS (search.normalize_arabic_v1(raw_text)) STORED,
  embedding extensions.vector(1024),
  token_count integer,
  page_number integer,
  section_path text[] NOT NULL DEFAULT '{}'::text[],
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  parent_chunk_id uuid REFERENCES app.document_chunks (id) ON DELETE SET NULL,
  deleted_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT document_chunks_chunk_index_nonnegative CHECK (chunk_index >= 0),
  CONSTRAINT document_chunks_unique_index UNIQUE (version_id, chunk_index)
);

COMMENT ON TABLE app.document_chunks IS
  'Authoritative passage text and Hybrid embedding (vector 1024). search_normalized is BM25/search-only.';

CREATE TABLE app.document_tables (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id uuid NOT NULL REFERENCES app.documents (id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES app.document_versions (id) ON DELETE CASCADE,
  table_name text NOT NULL,
  sheet_name text,
  parquet_bucket text,
  parquet_path text,
  row_count integer,
  column_count integer,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE app.document_table_columns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  table_id uuid NOT NULL REFERENCES app.document_tables (id) ON DELETE CASCADE,
  column_name text NOT NULL,
  column_type text NOT NULL,
  ordinal integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT document_table_columns_ordinal_nonnegative CHECK (ordinal >= 0),
  CONSTRAINT document_table_columns_unique_ordinal UNIQUE (table_id, ordinal)
);

CREATE TABLE app.document_search_terms (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  chunk_id uuid NOT NULL REFERENCES app.document_chunks (id) ON DELETE CASCADE,
  term text NOT NULL,
  term_normalized text GENERATED ALWAYS AS (search.normalize_arabic_v1(term)) STORED,
  weight numeric(8, 4) NOT NULL DEFAULT 1.0,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TABLE app.search_aliases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  alias text NOT NULL,
  canonical_term text NOT NULL,
  alias_normalized text GENERATED ALWAYS AS (search.normalize_arabic_v1(alias)) STORED,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE UNIQUE INDEX search_aliases_alias_uq
  ON app.search_aliases (alias_normalized);

CREATE TRIGGER document_chunks_touch_updated_at
  BEFORE UPDATE ON app.document_chunks
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER document_tables_touch_updated_at
  BEFORE UPDATE ON app.document_tables
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();

CREATE TRIGGER search_aliases_touch_updated_at
  BEFORE UPDATE ON app.search_aliases
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
