-- Phase 4 Packet 2: BM25 search index over the derived projection.
-- Tokenizer is pdb.unicode_words with no English stemmer. Key field is chunk_id.
-- Apply with the ParadeDB bootstrap role; paradedb_writer has DML only.

ALTER TABLE public.bm25_chunks ADD COLUMN IF NOT EXISTS content_hash text;

DROP INDEX IF EXISTS public.bm25_chunks_search_idx;

CREATE INDEX bm25_chunks_search_idx ON public.bm25_chunks
USING bm25 (
  chunk_id,
  (body_search::pdb.unicode_words),
  (coalesce(title_search, '')::pdb.unicode_words),
  (coalesce(heading_search, '')::pdb.unicode_words),
  (coalesce(alias_search, '')::pdb.unicode_words),
  language,
  acl_scope_id,
  is_current,
  visibility_generation
)
WITH (key_field = 'chunk_id');

COMMENT ON INDEX public.bm25_chunks_search_idx IS
  'pg_search BM25 index. Queries return canonical chunk_id only; no snippets.';
