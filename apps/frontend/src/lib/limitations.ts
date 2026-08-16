/**
 * Signed user-visible limitation copy. Codes match routing/SSE limitation
 * payloads. The UI never invents a bypass.
 */

const LIMITATION_COPY: Record<string, string> = {
  temporal_graph_limitation:
    "Historical and as-of relationship questions stay on Hybrid. The graph is current-version only.",
  graph_outage:
    "Graph retrieval is unavailable. Combined is relabeled to Hybrid; answers are not graph-only prose.",
  graph_updating:
    "The graph is not ready for these documents yet. Retrieval continues on Hybrid.",
  media_limitation:
    "This question needs media the current indexes cannot answer. The run refuses rather than guessing.",
  insufficient_evidence:
    "Retrieved evidence is insufficient. The answer is refused rather than overconfident.",
  coverage_gap:
    "Some requested sections are uncovered. The run reports gaps instead of filling them in.",
  negation_unresolved:
    "Negation scope is unresolved. The run asks for clarification or refuses.",
  source_unavailable:
    "A cited source was deleted after the run. History is not rewritten; the citation is marked unavailable.",
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
