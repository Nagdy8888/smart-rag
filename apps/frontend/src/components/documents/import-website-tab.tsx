/**
 * Website crawl tab. Controlled fields only; parent owns enqueue.
 */

import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { StatusBanner } from "../ui/status-banner";
import { isClassifiedApiError } from "../../lib/api";
import { apiFailureBanner } from "../../lib/failure-copy";
import styles from "./documents.module.css";

export type ImportWebsiteTabProps = {
  /** Attestation checkbox shared with the file tab. */
  attested: boolean;
  /** Attestation change. */
  onAttested: (value: boolean) => void;
  /** Paid handshake gate. */
  allowPaidPost: boolean;
  /** Crawl start URL. */
  startUrl: string;
  /** Start URL change. */
  onStartUrl: (value: string) => void;
  /** Approved domain. */
  approvedDomain: string;
  /** Domain change. */
  onApprovedDomain: (value: string) => void;
  /** Optional crawl document title. */
  crawlTitle: string;
  /** Crawl title change. */
  onCrawlTitle: (value: string) => void;
  /** Crawl depth 1–5. */
  maxDepth: number;
  /** Depth change. */
  onMaxDepth: (value: number) => void;
  /** Crawl pages 1–200. */
  maxPages: number;
  /** Pages change. */
  onMaxPages: (value: number) => void;
  /** Enqueue crawl. */
  onCrawl: () => void;
  /** Crawl mutation error. */
  crawlError: Error | null;
  /** Crawl success identifiers. */
  crawlNote: string | null;
  /** True while crawl POST is in flight. */
  crawlPending: boolean;
};

/**
 * Render the Website tab. Does not call FastAPI.
 *
 * @param props - Controlled crawl fields.
 * @returns Website form. URL policy remains a server decision.
 */
export function ImportWebsiteTab({
  attested,
  onAttested,
  allowPaidPost,
  startUrl,
  onStartUrl,
  approvedDomain,
  onApprovedDomain,
  crawlTitle,
  onCrawlTitle,
  maxDepth,
  onMaxDepth,
  maxPages,
  onMaxPages,
  onCrawl,
  crawlError,
  crawlNote,
  crawlPending,
}: ImportWebsiteTabProps) {
  return (
    <div className={styles.formStack}>
      <Input
        label="Start URL"
        value={startUrl}
        onChange={(event) => onStartUrl(event.target.value)}
      />
      <Input
        label="Approved domain"
        value={approvedDomain}
        onChange={(event) => onApprovedDomain(event.target.value)}
      />
      <Input
        label="Document title (optional)"
        value={crawlTitle}
        onChange={(event) => onCrawlTitle(event.target.value)}
      />
      <Input
        label="Max depth"
        type="number"
        min={1}
        max={5}
        value={String(maxDepth)}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) {
            onMaxDepth(Math.min(5, Math.max(1, Math.trunc(next))));
          }
        }}
      />
      <Input
        label="Max pages"
        type="number"
        min={1}
        max={200}
        value={String(maxPages)}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isFinite(next)) {
            onMaxPages(Math.min(200, Math.max(1, Math.trunc(next))));
          }
        }}
      />
      <label className={styles.checkLabel}>
        <input
          type="checkbox"
          checked={attested}
          onChange={(event) => onAttested(event.target.checked)}
        />{" "}
        I attest this website is an approved source under the current policy.
      </label>
      <Button
        type="button"
        variant="primary"
        data-action-id="documents.crawl"
        disabled={
          !allowPaidPost ||
          !attested ||
          startUrl.trim() === "" ||
          approvedDomain.trim() === ""
        }
        pending={crawlPending}
        pendingLabel="Adding…"
        onClick={onCrawl}
      >
        Add website
      </Button>
      {crawlNote ? <p className={styles.muted}>{crawlNote}</p> : null}
      {crawlError ? (
        <StatusBanner kind="error" role="alert">
          {isClassifiedApiError(crawlError)
            ? crawlError.failure.kind === "auth"
              ? "Crawl rejected. Members receive HTTP 403 from the server."
              : apiFailureBanner(crawlError.failure)
            : "Crawl rejected. Server authorization is authoritative."}
        </StatusBanner>
      ) : null}
    </div>
  );
}
