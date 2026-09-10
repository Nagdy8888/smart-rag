/**
 * Sources sheet for the current run. No preview or signed URLs.
 */

"use client";

import {
  citationChipName,
  citationSourceLabel,
} from "../../lib/citation-label";
import type { CitationResponse } from "../../lib/types";
import { SOURCE_PREVIEW_UNAVAILABLE } from "../../lib/citation-drawer";
import { CitationChip } from "../ui/citation-chip";
import { Sheet } from "../ui/sheet";
import styles from "./chat-transcript.module.css";

export type CitationSheetProps = {
  /** Whether the sheet is open. */
  open: boolean;
  /** Close handler. */
  onClose: () => void;
  /** Citations for the current run. */
  citations: CitationResponse[];
  /** Safe href builder. */
  hrefForCitation: (citation: CitationResponse) => string | undefined;
  /** Open the existing citation drawer from a chip. */
  onSelectCitation: (citation: CitationResponse, trigger: HTMLButtonElement) => void;
};

/**
 * Render a sources list in a sheet.
 *
 * @param props - Open state and citation rows.
 * @returns Sheet or null. Does not fetch signed source URLs.
 */
export function CitationSheet({
  open,
  onClose,
  citations,
  hrefForCitation,
  onSelectCitation,
}: CitationSheetProps) {
  if (!open) {
    return null;
  }
  return (
    <Sheet title={`Sources (${String(citations.length)})`} onClose={onClose}>
      {citations.length === 0 ? (
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
      <p className={styles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
    </Sheet>
  );
}
