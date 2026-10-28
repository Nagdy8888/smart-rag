/**
 * Sources sheet for the current run. No preview or signed URLs.
 */

"use client";

import {
  citationSourceLabel,
} from "../../lib/citation-label";
import { citationDisplayNumber, citationPageGroups, citationPageCountLabel } from "../../lib/citation-display";
import type { CitationResponse } from "../../lib/types";
import { Icon } from "../ui/icon";
import { Button } from "../ui/button";
import { CitationChip } from "../ui/citation-chip";
import { Sheet } from "../ui/sheet";
import styles from "./chat-transcript.module.css";
import sourceStyles from "./sources.module.css";

export type CitationSheetProps = {
  /** Whether the sheet is open. */
  open: boolean;
  pending?: boolean;
  error?: boolean;
  onRetry?: () => void;
  /** Close handler. */
  onClose: () => void;
  /** Citations for the current run. */
  citations: CitationResponse[];
  /** Safe href builder. */
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  /** Open the existing citation drawer from a chip. */
  onSelectCitation: (
    citation: CitationResponse,
    trigger: HTMLButtonElement,
  ) => void;
};

/**
 * Render a sources list in a sheet.
 *
 * @param props - Open state and citation rows.
 * @returns Sheet or null. Does not fetch signed source URLs.
 */
export function CitationSheet({
  open,
  pending = false,
  error = false,
  onRetry,
  onClose,
  citations,
  hrefForCitation,
  onSelectCitation,
}: CitationSheetProps) {
  if (!open) {
    return null;
  }
  return (
    <Sheet
      title={
        pending || error ? "Sources" : `Sources (${citationPageCountLabel(citations)})`
      }
      onClose={onClose}
      panelClassName={sourceStyles.sourcesPanel}
    >
      <div className={sourceStyles.intro}>
        <span className={sourceStyles.libraryMark} aria-hidden="true"><Icon name="documents" /></span>
        <h3>Follow the evidence</h3>
        <p>Open a source to read the supporting passage, then inspect its original page or website.</p>
      </div>
      {pending ? (
        <p role="status" className={styles.muted}>
          Loading sources…
        </p>
      ) : error ? (
        <div role="alert">
          <p>Sources could not be loaded. Your answer is still available.</p>
          {onRetry ? (
            <Button type="button" variant="secondary" onClick={onRetry}>
              Try again
            </Button>
          ) : null}
        </div>
      ) : citations.length === 0 ? (
        <p className={styles.muted}>No citations for this run yet.</p>
      ) : (
        <ul className={sourceStyles.sourceList}>
          {citationPageGroups(citations).map((group) => { const citation = group[0]!; return (
            <li key={citation.citation_id} className={sourceStyles.sourceCard}>
              <p className={sourceStyles.sourceKind}><Icon name={citation.source_kind === "web" ? "search" : "documents"} />{citation.source_kind === "web" ? "Web source" : "Company source"}</p>
              {group.length > 1 ? <p>{citationSourceLabel(citation)}</p> : null}
              {group.map((citation) => <CitationChip
                key={citation.citation_id}
                index={citationDisplayNumber(citation, citations)}
                label={group.length > 1 ? `Supporting passage ${citationDisplayNumber(citation, citations)}` : citation.source_kind === "web" ? citationSourceLabel(citation) : citationSourceLabel(citation).replace(/[-_]/g, " ").replace(/\.pdf(?=\s|$)/i, "")}
                name={`Citation ${citationDisplayNumber(citation, citations)}, ${citationSourceLabel(citation)}`}
                unavailable={citation.source_unavailable}
                href={hrefForCitation(citation)}
                onSelect={(trigger) => {
                  onSelectCitation(citation, trigger);
                }}
              />)}
            </li>
          ); })}
        </ul>
      )}
      {!pending && !error && citations.length > 0 ? (
        <p className={styles.muted}>
          Select a citation to inspect its supporting passage and available
          page.
        </p>
      ) : null}
    </Sheet>
  );
}
