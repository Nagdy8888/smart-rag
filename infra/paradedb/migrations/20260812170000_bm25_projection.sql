-- Phase 2 Packet 2: rebuildable BM25 projection (derived; no canonical authority).

CREATE TABLE IF NOT EXISTS bm25_index_meta (
  id integer PRIMARY KEY DEFAULT 1,
  index_version integer NOT NULL DEFAULT 1,
  normalization_version text NOT NULL DEFAULT 'arabic_norm_v1',
  index_schema_version text NOT NULL DEFAULT 'bm25_v1',
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT bm25_index_meta_singleton CHECK (id = 1)
);

INSERT INTO bm25_index_meta (id)
VALUES (1)
ON CONFLICT (id) DO NOTHING;

CREATE TABLE IF NOT EXISTS bm25_chunks (
  chunk_id uuid PRIMARY KEY,
  version_id uuid NOT NULL,
  document_id uuid NOT NULL,
  title_search text,
  heading_search text,
  alias_search text,
  body_search text NOT NULL,
  language text,
  effective_at timestamptz,
  tag text,
  authority_rank smallint,
  is_current boolean NOT NULL DEFAULT true,
  visibility_generation bigint NOT NULL DEFAULT 1,
  acl_scope_id text NOT NULL,
  indexed_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  normalization_version text NOT NULL DEFAULT 'arabic_norm_v1'
);

COMMENT ON TABLE bm25_chunks IS
  'Derived lexical projection keyed by canonical chunk/version IDs. Rebuildable from Supabase.';
COMMENT ON COLUMN bm25_chunks.acl_scope_id IS
  'Opaque ACL scope hash/ID for prefilters; authorization recheck remains mandatory in Supabase.';
COMMENT ON COLUMN bm25_chunks.body_search IS
  'search.normalize_arabic_v1 output applied at projection time; never raw citation text.';

CREATE INDEX IF NOT EXISTS bm25_chunks_version_id_idx
  ON bm25_chunks (version_id);

CREATE INDEX IF NOT EXISTS bm25_chunks_document_id_idx
  ON bm25_chunks (document_id);

CREATE INDEX IF NOT EXISTS bm25_chunks_visibility_generation_idx
  ON bm25_chunks (visibility_generation);

CREATE INDEX IF NOT EXISTS bm25_chunks_acl_scope_id_idx
  ON bm25_chunks (acl_scope_id);

-- BM25 index DDL (pg_search) is Phase 4-owned once projection rows exist.
