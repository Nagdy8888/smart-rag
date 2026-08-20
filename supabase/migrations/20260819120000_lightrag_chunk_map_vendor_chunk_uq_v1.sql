-- Expand-only unique vendor-chunk mapping so one LightRAG chunk cannot
-- overwrite another canonical passage. PK on chunk_id already enforces
-- one map per canonical chunk.

CREATE UNIQUE INDEX IF NOT EXISTS lightrag_chunk_map_vendor_chunk_uq
  ON app.lightrag_chunk_map (workspace_key, version_id, lightrag_chunk_id)
  WHERE version_id IS NOT NULL
    AND workspace_key IS NOT NULL
    AND lightrag_chunk_id IS NOT NULL;

COMMENT ON INDEX app.lightrag_chunk_map_vendor_chunk_uq IS
  'One vendor chunk maps to at most one canonical passage per workspace/version.';
