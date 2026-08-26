/**
 * Graph search and inspect OpenAPI types.
 *
 * Field names match `docs/api/openapi.foundation.json`.
 */

/** `GET /graph/entities/search` hit. No vendor prose. */
export type GraphEntityResponse = {
  object_id: string;
  object_type: string;
  chunk_id: string;
  document_id: string;
  version_id: string;
  support: number;
};

/** `POST /graph/inspect` body. Depth is 1–3. */
export type GraphInspectRequest = {
  entity_keys: string[];
  document_id?: string | null;
  depth: number;
};

/** Authorized inspect node. No document title field. */
export type GraphInspectNodeResponse = {
  object_type: string;
  object_id: string;
  chunk_id: string;
  document_id: string;
  version_id: string;
  support: number;
  hop: number;
};

/** Canonical locator coordinates. Never vendor chunk text. */
export type GraphInspectLocator = {
  chunk_id: string;
  document_id: string;
  version_id: string;
  page_number: number | null;
  section_path: string[];
  sheet_name: string | null;
  range_ref: string | null;
  source_url: string | null;
};

/** Typed inspect limitation. ACL blindness must ignore `count`. */
export type GraphInspectLimitation = {
  code: string;
  count: number | null;
};

/** `POST /graph/inspect` payload. At most 200 rows. */
export type GraphInspectResponse = {
  nodes: GraphInspectNodeResponse[];
  locators: GraphInspectLocator[];
  limitations: GraphInspectLimitation[];
  row_count: number;
  depth: number;
};
