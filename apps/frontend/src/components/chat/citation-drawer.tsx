/**
 * Citation side sheet. Presentation only; the page image is fetched here.
 *
 * The book page is the first thing in the panel. The quoted passage sits
 * under it. No Storage URL.
 */

"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { fetchCitationPagePng, type ApiAuth } from "../../lib/api";
import { SOURCE_PREVIEW_UNAVAILABLE } from "../../lib/citation-drawer";
import {
  LEGACY_EXCERPT_COPY,
  citationDrawerTitle,
  citationLocatorFields,
} from "../../lib/citation-label";
import { limitationCopy } from "../../lib/limitations";
import type { CitationResponse } from "../../lib/types";
import overlayStyles from "../ui/styles/overlays.module.css";
import { LimitationCallout } from "../ui/limitation-callout";
import { Sheet } from "../ui/sheet";
import { UserText } from "../ui/user-text";
import chatStyles from "./chat-transcript.module.css";

/** Copy while the citation detail request has not returned the span. */
export const CITATION_PASSAGE_LOADING = "Loading passage…";

/** Copy while the single-page PNG is downloading. */
export const CITATION_PAGE_LOADING = "Loading page…";

/** Copy when the page image request fails. The passage still shows. */
export const CITATION_PAGE_FAILED = "The book page could not be loaded.";

export type CitationPageSource = {
  auth: ApiAuth;
  runId: string;
  citationId: string;
};

export type CitationDrawerProps = {
  citation: CitationResponse | null;
  /** True while the detail request for this citation is still in flight. */
  passagePending?: boolean;
  /** Present when a company PDF page image may be fetched. */
  pageSource?: CitationPageSource | null;
  /** Page image loader. Tests replace the network call. */
  loadPage?: (source: CitationPageSource) => Promise<Blob>;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * Render the citation as a right-side sheet.
 *
 * Escape, the backdrop, and focus return are handled by the sheet.
 * No privileged href and no Storage download.
 *
 * @param props - Selected citation, page request, and close handler.
 * @returns Side sheet, or null when closed.
 */
export function CitationDrawer({
  citation,
  passagePending = false,
  pageSource = null,
  loadPage = (source) =>
    fetchCitationPagePng(source.auth, source.runId, source.citationId),
  onClose,
  returnFocusRef,
}: CitationDrawerProps) {
  const [pageUrl, setPageUrl] = useState<string | null>(null);
  const [pagePending, setPagePending] = useState(false);
  const [pageFailed, setPageFailed] = useState(false);
  const pageRunId = pageSource?.runId ?? null;
  const pageCitationId = pageSource?.citationId ?? null;
  const pageToken = pageSource?.auth.accessToken ?? null;
  const loadPageRef = useRef(loadPage);
  loadPageRef.current = loadPage;

  useEffect(() => {
    if (pageRunId === null || pageCitationId === null || pageToken === null) {
      setPageUrl(null);
      setPagePending(false);
      setPageFailed(false);
      return;
    }
    const source: CitationPageSource = {
      auth: { accessToken: pageToken },
      runId: pageRunId,
      citationId: pageCitationId,
    };
    let cancelled = false;
    let objectUrl: string | null = null;
    setPagePending(true);
    setPageFailed(false);
    setPageUrl(null);
    void loadPageRef.current(source)
      .then((blob) => {
        if (cancelled) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setPageUrl(objectUrl);
        setPagePending(false);
      })
      .catch(() => {
        if (cancelled) {
          return;
        }
        setPageFailed(true);
        setPagePending(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [pageCitationId, pageRunId, pageToken]);

  if (citation === null) {
    return null;
  }
  const fields = citationLocatorFields(citation);
  const excerpt =
    citation.source_unavailable || typeof citation.evidence_excerpt !== "string"
      ? null
      : citation.evidence_excerpt;
  return (
    <Sheet
      title={citationDrawerTitle(citation)}
      side="right"
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      panelClassName={overlayStyles.citationSheet}
    >
      {pagePending ? (
        <p className={chatStyles.muted}>{CITATION_PAGE_LOADING}</p>
      ) : null}
      {pageFailed ? <p className={chatStyles.muted}>{CITATION_PAGE_FAILED}</p> : null}
      {pageUrl !== null ? (
        <img
          className={chatStyles.citationPageImage}
          src={pageUrl}
          alt={citationDrawerTitle(citation)}
        />
      ) : null}
      {passagePending ? (
        <p className={chatStyles.muted}>{CITATION_PASSAGE_LOADING}</p>
      ) : excerpt !== null ? (
        <div>
          <p className={chatStyles.supportingPassageLabel}>Supporting passage</p>
          <p className={chatStyles.supportingPassage} dir="auto">
            <UserText value={excerpt} />
          </p>
        </div>
      ) : citation.source_unavailable ? null : (
        <p className={chatStyles.muted}>{LEGACY_EXCERPT_COPY}</p>
      )}
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
      {!passagePending && citation.source_unavailable ? (
        <LimitationCallout tone="warning">
          {limitationCopy("source_unavailable")}
        </LimitationCallout>
      ) : null}
      {!passagePending && excerpt === null ? (
        <p className={chatStyles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
      ) : null}
    </Sheet>
  );
}
