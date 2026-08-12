-- Phase 2 Packet 2: LightRAG canonical mapping tables and entity curation rules.

CREATE TABLE app.lightrag_source_map (
  document_id uuid PRIMARY KEY REFERENCES app.documents (id) ON DELETE CASCADE,
  lightrag_workspace text NOT NULL DEFAULT 'default',
  lightrag_doc_id text NOT NULL,
  mapped_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT lightrag_source_map_doc_id_nonempty CHECK (btrim(lightrag_doc_id) <> '')
);

COMMENT ON TABLE app.lightrag_source_map IS
  'Maps canonical documents to LightRAG document IDs. Graph engine storage remains private.';

CREATE TABLE app.lightrag_chunk_map (
  chunk_id uuid PRIMARY KEY REFERENCES app.document_chunks (id) ON DELETE CASCADE,
  lightrag_doc_id text NOT NULL,
  lightrag_chunk_id text NOT NULL,
  mapped_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT lightrag_chunk_map_ids_nonempty CHECK (
    btrim(lightrag_doc_id) <> '' AND btrim(lightrag_chunk_id) <> ''
  )
);

CREATE TABLE app.graph_evidence_map (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  graph_object_type text NOT NULL,
  graph_object_id text NOT NULL,
  chunk_id uuid NOT NULL REFERENCES app.document_chunks (id) ON DELETE CASCADE,
  confidence numeric(5, 4) NOT NULL DEFAULT 1.0,
  mapped_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  CONSTRAINT graph_evidence_map_confidence_range CHECK (
    confidence >= 0 AND confidence <= 1
  )
);

CREATE UNIQUE INDEX graph_evidence_map_object_chunk_uq
  ON app.graph_evidence_map (graph_object_type, graph_object_id, chunk_id);

CREATE TABLE app.graph_entity_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  entity_type text NOT NULL,
  rule jsonb NOT NULL DEFAULT '{}'::jsonb,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT timezone('utc', now()),
  updated_at timestamptz NOT NULL DEFAULT timezone('utc', now())
);

CREATE TRIGGER graph_entity_rules_touch_updated_at
  BEFORE UPDATE ON app.graph_entity_rules
  FOR EACH ROW
  EXECUTE FUNCTION app.touch_updated_at();
