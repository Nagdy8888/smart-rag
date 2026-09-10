/**
 * Citation inspector drawer. Presentation only; no fetch.
 */

"use client";

import type { RefObject } from "react";
import { SOURCE_PREVIEW_UNAVAILABLE } from "../../lib/citation-drawer";
import { citationLocatorFields } from "../../lib/citation-label";
import { limitationCopy } from "../../lib/limitations";
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
 * Render citation locators and technical ids. No privileged href and no snippet HTML.
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
  const fields = citationLocatorFields(citation);
  const page =
    fields.locators.find((item) => item.key === "page_label") ??
    fields.locators.find((item) => item.key === "page_number");
  const title =
    page === undefined
      ? `Citation ${String(citation.citation_index)}`
      : `Page ${page.value}`;
  return (
    <Drawer title={title} onClose={onClose} returnFocusRef={returnFocusRef}>
      <dl className={chatStyles.sourceDl}>
        {fields.locators.map((item) => (
          <div key={item.key}>
            <dt>{item.label}</dt>
            <dd>
              <UserText value={item.value} />
            </dd>
          </div>
        ))}
        {fields.technical.map((item) => (
          <div key={item.key}>
            <dt>{item.label}</dt>
            <dd>
              <UserText value={item.value} />
            </dd>
          </div>
        ))}
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
