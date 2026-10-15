/**
 * Citation passage popup. Presentation only; no fetch.
 *
 * Anchored to the chip that opened it. Shows the book, Acrobat page, and
 * the authorized supporting span. No PDF page image and no Storage URL.
 */

"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState, type RefObject } from "react";
import { fetchCitationPagePng, type ApiAuth } from "../../lib/api";
import { SOURCE_PREVIEW_UNAVAILABLE } from "../../lib/citation-drawer";
import {
  LEGACY_EXCERPT_COPY,
  citationDrawerTitle,
  citationLocatorFields,
} from "../../lib/citation-label";
import { limitationCopy } from "../../lib/limitations";
import type { CitationResponse } from "../../lib/types";
import { Button } from "../ui/button";
import { trapFocus } from "../ui/focus-trap";
import overlayStyles from "../ui/styles/overlays.module.css";
import { LimitationCallout } from "../ui/limitation-callout";
import { UserText } from "../ui/user-text";
import chatStyles from "./chat-transcript.module.css";

/** Copy while the citation detail request has not returned the span. */
export const CITATION_PASSAGE_LOADING = "Loading passage…";

/** Copy while the single-page PNG is downloading. */
export const CITATION_PAGE_LOADING = "Loading page…";

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
 * Place the popup under the chip, flipping above when the viewport is short.
 *
 * @param panel - Popup element.
 * @param trigger - Chip that opened it, or null.
 */
function placeCitationPopup(
  panel: HTMLElement,
  trigger: HTMLElement | null,
): void {
  const width = panel.offsetWidth;
  const height = panel.offsetHeight;
  if (trigger === null) {
    panel.style.top = "16px";
    panel.style.left = "16px";
    return;
  }
  const rect = trigger.getBoundingClientRect();
  let top = rect.bottom + 8;
  let left = rect.left;
  if (top + height > window.innerHeight - 8) {
    top = Math.max(8, rect.top - height - 8);
  }
  if (left + width > window.innerWidth - 8) {
    left = Math.max(8, window.innerWidth - width - 8);
  }
  panel.style.top = `${String(top)}px`;
  panel.style.left = `${String(left)}px`;
}

/**
 * Render the citation popup next to the opening chip.
 *
 * Escape and a click outside the popup close it. Focus returns to the chip.
 * No privileged href, no snippet HTML, and no Storage download.
 *
 * @param props - Selected citation, pending flag, and close handler.
 * @returns Popup dialog, or null when closed.
 */
export function CitationDrawer({
  citation,
  passagePending = false,
  pageSource = null,
  loadPage = fetchCitationPagePng,
  onClose,
  returnFocusRef,
}: CitationDrawerProps) {
  const containerRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const [pageUrl, setPageUrl] = useState<string | null>(null);
  const [pagePending, setPagePending] = useState(false);
  const pageRunId = pageSource?.runId ?? null;
  const pageCitationId = pageSource?.citationId ?? null;
  const pageToken = pageSource?.auth.accessToken ?? null;

  useEffect(() => {
    if (pageSource === null || pageRunId === null || pageCitationId === null) {
      setPageUrl(null);
      setPagePending(false);
      return;
    }
    const source = pageSource;
    let cancelled = false;
    let objectUrl: string | null = null;
    setPagePending(true);
    setPageUrl(null);
    void loadPage(source)
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
        setPagePending(false);
      });
    return () => {
      cancelled = true;
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [loadPage, pageCitationId, pageRunId, pageSource, pageToken]);

  useLayoutEffect(() => {
    const panel = containerRef.current;
    if (panel === null) {
      return;
    }
    const place = (): void => {
      placeCitationPopup(panel, returnFocusRef?.current ?? null);
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [citation, passagePending, returnFocusRef]);

  useEffect(() => {
    const root = containerRef.current;
    if (root === null) {
      return;
    }
    const release = trapFocus(root, {
      returnFocus: returnFocusRef?.current ?? null,
    });
    return release;
  }, [returnFocusRef]);

  useEffect(() => {
    const root = containerRef.current;
    if (root === null) {
      return;
    }
    /**
     * Close when the pointer lands outside the popup and the opening chip.
     *
     * @param event - Document pointer event.
     */
    function onPointerDown(event: PointerEvent): void {
      const target = event.target;
      if (!(target instanceof Node) || root === null) {
        return;
      }
      if (root.contains(target)) {
        return;
      }
      if (returnFocusRef?.current?.contains(target)) {
        return;
      }
      onClose();
    }
    /**
     * Close on Escape from anywhere while the popup is open.
     *
     * @param event - Document keyboard event.
     */
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== "Escape") {
        return;
      }
      event.preventDefault();
      onClose();
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [onClose, returnFocusRef]);

  if (citation === null) {
    return null;
  }
  const fields = citationLocatorFields(citation);
  const excerpt =
    citation.source_unavailable || typeof citation.evidence_excerpt !== "string"
      ? null
      : citation.evidence_excerpt;
  return (
    <aside
      ref={containerRef}
      className={overlayStyles.citationPopup}
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className={overlayStyles.drawerHeader}>
        <h3 id={titleId}>{citationDrawerTitle(citation)}</h3>
        <Button type="button" onClick={onClose}>
          Close
        </Button>
      </div>
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
      {pagePending ? (
        <p className={chatStyles.muted}>{CITATION_PAGE_LOADING}</p>
      ) : null}
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
      {!passagePending && citation.source_unavailable ? (
        <LimitationCallout tone="warning">
          {limitationCopy("source_unavailable")}
        </LimitationCallout>
      ) : null}
      {!passagePending && excerpt === null ? (
        <p className={chatStyles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
      ) : null}
    </aside>
  );
}
