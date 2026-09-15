/**
 * Citation inspector drawer. Presentation only; no fetch.
 */

"use client";

import type { RefObject } from "react";
import { SOURCE_PREVIEW_UNAVAILABLE } from "../../lib/citation-drawer";
import {
  LEGACY_EXCERPT_COPY,
  citationDrawerTitle,
  citationLocatorFields,
} from "../../lib/citation-label";
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
 * Render citation locators, optional supporting passage, and technical ids.
 *
 * No privileged href, no snippet HTML, and no Storage download.
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
  const excerpt =
    citation.source_unavailable || typeof citation.evidence_excerpt !== "string"
      ? null
      : citation.evidence_excerpt;
  return (
    <Drawer
      title={citationDrawerTitle(citation)}
      onClose={onClose}
      returnFocusRef={returnFocusRef}
    >
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
      {excerpt !== null ? (
        <div>
          <p className={chatStyles.supportingPassageLabel}>Supporting passage</p>
          <p className={chatStyles.supportingPassage} dir="auto">
            <UserText value={excerpt} />
          </p>
        </div>
      ) : citation.source_unavailable ? null : (
        <p className={chatStyles.muted}>{LEGACY_EXCERPT_COPY}</p>
      )}
      {citation.source_unavailable ? (
        <LimitationCallout tone="warning">
          {limitationCopy("source_unavailable")}
        </LimitationCallout>
      ) : null}
      {excerpt === null ? (
        <p className={chatStyles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
      ) : null}
    </Drawer>
  );
}
