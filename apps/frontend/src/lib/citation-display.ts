/** Display-only citation mapping. Stored identities and indices never change. */
import type { CitationResponse } from "./types";

export function citationDisplayNumber(citation: CitationResponse, citations: readonly CitationResponse[]): number {
  const ordered = [...citations].sort((a, b) => a.citation_index - b.citation_index);
  return Math.max(1, ordered.findIndex((item) => item.citation_id === citation.citation_id) + 1);
}

export function citationPageGroups(citations: readonly CitationResponse[]): CitationResponse[][] {
  const groups = new Map<string, CitationResponse[]>();
  for (const citation of citations) {
    let key = citation.citation_id;
    if (citation.source_kind === "web") {
      const raw = citation.source_url ?? citation.provenance.url;
      if (typeof raw === "string") {
        try {
          const url = new URL(raw);
          url.hash = "";
          key = `web:${url.href}`;
        } catch { /* Keep malformed or unavailable identities separate. */ }
      }
    }
    const group = groups.get(key) ?? [];
    group.push(citation);
    groups.set(key, group);
  }
  return [...groups.values()];
}


export function citationPageCountLabel(citations: readonly CitationResponse[]): string {
  const count = citationPageGroups(citations).length;
  return `${count} ${count === 1 ? "page" : "pages"}`;
}

/** Clipboard text uses the same display mapping as the visible reference. */
export function citationCopyText(text: string, citations: readonly CitationResponse[]): string {
  return text.replace(/\[\[cite:(\d+)\]\]/g, (_, index: string) => {
    const citation = citations.find(item => item.citation_index === Number(index));
    return citation ? `[${citationDisplayNumber(citation, citations)}]` : "[Source unavailable]";
  });
}
