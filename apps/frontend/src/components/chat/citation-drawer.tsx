/**
 * Citation inspector drawer. Presentation only; no fetch.
 */

"use client";

import type { RefObject } from "react";
import {
  SOURCE_PREVIEW_UNAVAILABLE,
} from "../../lib/citation-drawer";
import { limitationCopy } from "../../lib/limitations";
import { formatProvenance } from "../../lib/safe-text";
import type { CitationResponse } from "../../lib/types";
import { Drawer } from "../ui/drawer";
import { LimitationCallout } from "../ui/limitation-callout";
import { UserText } from "../ui/user-text";
import chatStyles from "./chat-transcript.module.css";

export type CitationDrawerProps = {
  citation: CitationResponse | null;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * Render citation ids and provenance. No privileged href and no snippet HTML.
 *
 * @param props - Selected citation or null.
 * @returns Drawer region, or null when closed.
 */
export function CitationDrawer({
  citation,
  onClose,
  returnFocusRef,
}: CitationDrawerProps) {
  if (citation === null) {
    return null;
  }
  return (
    <Drawer
      title={`Citation ${String(citation.citation_index)}`}
      onClose={onClose}
      returnFocusRef={returnFocusRef}
    >
      <dl>
        <dt>citation_id</dt>
        <dd>
          <UserText value={citation.citation_id} />
        </dd>
        <dt>chunk_id</dt>
        <dd>
          <UserText value={citation.chunk_id ?? "none"} />
        </dd>
        <dt>provenance</dt>
        <dd>
          <UserText value={formatProvenance(citation.provenance) || "none"} />
        </dd>
      </dl>
      {citation.source_unavailable ? (
        <LimitationCallout tone="warning">
          {limitationCopy("source_unavailable")}
        </LimitationCallout>
      ) : null}
      <p className={chatStyles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
    </Drawer>
  );
}
