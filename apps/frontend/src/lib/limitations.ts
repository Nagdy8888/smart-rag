/**
 * Signed user-visible limitation copy. Codes match routing/SSE limitation
 * payloads. The UI never invents a bypass.
 */

/** Company refusal when retrieved sources cannot support an answer. */
export const INSUFFICIENT_EVIDENCE_COPY =
  "Company sources could not support an answer. Narrow the question and try again.";

const LIMITATION_COPY: Record<string, string> = {
  temporal_graph_limitation:
    "Historical and as-of relationship questions stay on Hybrid. The graph is current-version only.",
  graph_outage:
    "Graph retrieval is unavailable. Combined is relabeled to Hybrid; answers are not graph-only prose.",
  bm25_unavailable:
    "Private BM25 is unavailable. Retrieval continues as dense plus exact/trigram term Hybrid. BM25 snippets are not evidence.",
  graph_updating:
    "The graph is not ready for these documents yet. Retrieval continues on Hybrid.",
  media_limitation:
    "This question needs media the current indexes cannot answer. The run refuses rather than guessing.",
  insufficient_evidence: INSUFFICIENT_EVIDENCE_COPY,
  coverage_gap:
    "Some requested sections are uncovered. The run reports gaps instead of filling them in.",
  negation_unresolved:
    "Negation scope is unresolved. The run asks for clarification or refuses.",
  source_unavailable:
    "A cited source was deleted after the run. History is not rewritten; the citation is marked unavailable.",
  graph_partial_readiness:
    "Some authorized documents are not yet in the graph. Retrieval continues on Hybrid.",
  graph_acl_blindness: "Some sources you cannot access are omitted.",
  graph_survival_below_threshold:
    "Graph support is below the survival threshold. Combined is relabeled to Hybrid.",
  graph_filtered_dirty:
    "Dirty graph changes are filtered. Retrieval continues on authorized Hybrid evidence.",
  global_steering_only:
    "Graph output is steering only. Final answers use Hybrid evidence.",
  graph_empty: "No authorized graph objects are available for this inspect.",
  graph_deadline: "Graph inspection stopped at the deadline. Results are partial.",
  graph_cancelled: "Graph inspection was cancelled.",
  graph_pending:
    "The graph is not ready for these documents yet. Hybrid remains usable. Graph-only is not an answering mode.",
  retrievers_unbound:
    "Retrieval was not attached to this run. Answers are not grounded in Hybrid or graph evidence.",
};

/**
 * Return signed copy for a limitation code.
 *
 * @param code - SSE `limitation.code` or citation flag.
 * @returns Signed sentence, or the code itself when unknown.
 */
export function limitationCopy(code: string): string {
  const known = LIMITATION_COPY[code];
  if (known !== undefined) {
    return known;
  }
  return code;
}

/**
 * Return the graph-readiness sentence for an authorized not-ready count.
 *
 * Never include restricted or ineligible counts.
 *
 * @param authorizedNotReadyCount - Count of relevant recent docs not in graph.
 * @returns User-visible sentence.
 */
export function graphNotReadyCopy(authorizedNotReadyCount: number): string {
  const count = Math.max(0, Math.floor(authorizedNotReadyCount));
  return `${count} relevant recent documents are not yet represented in the graph`;
}

/**
 * Return the callout tone for a limitation code.
 *
 * BM25 degrade and Graph Pending stay warning, not danger.
 *
 * @param _code - Limitation code.
 * @returns Always `warning`. Never danger for BM25 or Graph Pending.
 */
export function limitationTone(_code: string): "warning" {
  void _code;
  return "warning";
}

/**
 * Return whether graph-only inspection is being presented as an answering
 * success. Graph-only is never a success answering mode.
 *
 * @param routeFamily - Server `route_family`.
 * @returns True when the UI must label inspection, not an answer.
 */
export function isGraphOnlyInspectionRoute(
  routeFamily: string | null,
): boolean {
  return routeFamily === "graph_inspection";
}
