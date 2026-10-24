/**
 * Citation side sheet. Presentation only; the page image is fetched here.
 *
 * The book page is the first thing in the panel. The quoted passage sits
 * under it. No Storage URL.
 */

"use client";

import { useEffect, useState, type RefObject } from "react";
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
import { Button } from "../ui/button";
import sourceStyles from "./sources.module.css";
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
  /** Return to the citations for the same answer. */
  onBack?: () => void;
  /** Authorized citation list for the current answer only. */
  citations?: readonly CitationResponse[];
  onNavigateCitation?: (citationId: string) => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/** Fetch the authorized page through the API using a stable loader identity. */
function loadCitationPage(source: CitationPageSource): Promise<Blob> {
  return fetchCitationPagePng(source.auth, source.runId, source.citationId);
}

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
  loadPage = loadCitationPage,
  onClose,
  onBack,
  citations = [],
  onNavigateCitation,
  returnFocusRef,
}: CitationDrawerProps) {

  if (citation === null) {
    return null;
  }
  const citationPosition = citations.findIndex((item) => item.citation_id === citation.citation_id);
  const fields = citationLocatorFields(citation);
  const excerpt =
    citation.source_unavailable || typeof citation.evidence_excerpt !== "string"
      ? null
      : citation.evidence_excerpt;
  return (
    <Sheet
      title={citationDrawerTitle(citation).replace(/[-_]/g, " ").replace(/\.pdf(?=\s|$)/i, "")}
      side="right"
      onClose={onClose}
      returnFocusRef={returnFocusRef}
      panelClassName={`${overlayStyles.citationSheet} ${sourceStyles.readerPanel}`}
    >
      {onBack || (citationPosition >= 0 && onNavigateCitation) ? (
        <nav className={sourceStyles.citationNavigation} aria-label="Citation navigation">
          {onBack ? <Button type="button" variant="secondary" size="compact" onClick={onBack}>Back to sources</Button> : null}
          {citationPosition >= 0 && onNavigateCitation ? (
            <div className={sourceStyles.citationPager}>
              <Button type="button" variant="ghost" size="compact" aria-label="Previous citation" disabled={citationPosition === 0} onClick={() => { const previous = citations[citationPosition - 1]; if (previous) onNavigateCitation(previous.citation_id); }}>Previous</Button>
              <span aria-live="polite">{citationPosition + 1} of {citations.length}</span>
              <Button type="button" variant="ghost" size="compact" aria-label="Next citation" disabled={citationPosition >= citations.length - 1} onClick={() => { const next = citations[citationPosition + 1]; if (next) onNavigateCitation(next.citation_id); }}>Next</Button>
            </div>
          ) : null}
        </nav>
      ) : null}
      {pageSource !== null ? (
        <CitationPagePreview
          key={JSON.stringify([pageSource.runId, pageSource.citationId, pageSource.auth.accessToken])}
          pageSource={pageSource}
          loadPage={loadPage}
          title={citationDrawerTitle(citation)}
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

      </dl>
      <details className={sourceStyles.technical}>
        <summary>Source details</summary>
        <dl className={chatStyles.sourceDl}>
        {fields.technical.map((item) => (
          <div key={item.key}>
            <dt>{item.label}</dt>
            <dd>
              <UserText value={item.value} />
            </dd>
          </div>
        ))}
        </dl>
      </details>
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

/** Own the image request for one selection; changing selection releases its URL. */
function CitationPagePreview({pageSource, loadPage, title}: {
  pageSource: CitationPageSource;
  loadPage: NonNullable<CitationDrawerProps["loadPage"]>;
  title: string;
}) {
  const [zoom, setZoom] = useState(100);
  const [pageResult, setPageResult] = useState<{
    runId: string;
    citationId: string;
    token: string;
    loader: typeof loadPage;
    url: string | null;
    failed: boolean;
  } | null>(null);
  const pageRunId = pageSource?.runId ?? null;
  const pageCitationId = pageSource?.citationId ?? null;
  const pageToken = pageSource?.auth.accessToken ?? null;
  const hasPageSource = pageRunId !== null && pageCitationId !== null && pageToken !== null;
  const currentResult = hasPageSource &&
    pageResult?.runId === pageRunId &&
    pageResult?.citationId === pageCitationId &&
    pageResult?.token === pageToken &&
    pageResult?.loader === loadPage ? pageResult : null;
  const pageUrl = currentResult?.url ?? null;
  const pagePending = hasPageSource && currentResult === null;
  const pageFailed = currentResult?.failed ?? false;

  useEffect(() => {
    if (pageRunId === null || pageCitationId === null || pageToken === null) {
      return;
    }
    const source: CitationPageSource = {
      auth: { accessToken: pageToken },
      runId: pageRunId,
      citationId: pageCitationId,
    };
    let cancelled = false;
    let objectUrl: string | null = null;
    const identity = {runId: pageRunId, citationId: pageCitationId, token: pageToken, loader: loadPage};
    void loadPage(source)
      .then((blob) => {
        if (cancelled) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setPageResult({...identity, url: objectUrl, failed: false});
      })
      .catch(() => {
        if (!cancelled) {
          setPageResult({...identity, url: null, failed: true});
        }
      });
    return () => {
      cancelled = true;
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [pageCitationId, pageRunId, pageToken, loadPage]);
  return <>
      {pagePending ? (
        <p className={chatStyles.muted}>{CITATION_PAGE_LOADING}</p>
      ) : null}
      {pageFailed ? <p className={chatStyles.muted}>{CITATION_PAGE_FAILED}</p> : null}
      {pageUrl !== null ? (
        <div className={sourceStyles.pageReader}>
          <div className={sourceStyles.readerToolbar}>
            <span>Original page</span>
            <div className={sourceStyles.zoomControls} role="group" aria-label="Page zoom">
              <Button type="button" variant="ghost" size="compact" aria-label="Zoom out" disabled={zoom <= 100} onClick={() => setZoom((value) => Math.max(100, value - 25))}>-</Button>
              <Button type="button" variant="ghost" size="compact" aria-label="Fit page" onClick={() => setZoom(100)}>{zoom}%</Button>
              <Button type="button" variant="ghost" size="compact" aria-label="Zoom in" disabled={zoom >= 200} onClick={() => setZoom((value) => Math.min(200, value + 25))}>+</Button>
            </div>
          </div>
          <p className={sourceStyles.highlightHint}><span aria-hidden="true" />Yellow marks cited text found on this page. Figure descriptions and very short fragments may have no highlight.</p>
          <div className={sourceStyles.pageViewport} tabIndex={0} role="region" aria-label="Original source page">
            <img className={sourceStyles.pageImage} style={{width: `${zoom}%`}} src={pageUrl} alt={title} />
          </div>
        </div>
      ) : null}
  </>;
}
