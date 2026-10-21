/**
 * Sources sheet for the current run. No preview or signed URLs.
 */

"use client";

import {
  citationChipName,
  citationSourceLabel,
} from "../../lib/citation-label";
import type { CitationResponse } from "../../lib/types";
import { Button } from "../ui/button";
import { CitationChip } from "../ui/citation-chip";
import { Sheet } from "../ui/sheet";
import styles from "./chat-transcript.module.css";

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
        pending || error ? "Sources" : `Sources (${String(citations.length)})`
      }
      onClose={onClose}
    >
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
        <ul className={styles.citationList}>
          {citations.map((citation) => (
            <li key={citation.citation_id}>
              <CitationChip
                index={citation.citation_index}
                label={citationSourceLabel(citation)}
                name={citationChipName(citation)}
                unavailable={citation.source_unavailable}
                href={hrefForCitation(citation)}
                onSelect={(trigger) => {
                  onSelectCitation(citation, trigger);
                }}
              />
            </li>
          ))}
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
