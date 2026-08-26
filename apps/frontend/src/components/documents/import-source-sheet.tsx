/**
 * Import source sheet: Files and Website tabs gated by role convenience helpers.
 */

import type { ChangeEvent } from "react";
import { Button } from "../ui/button";
import { FileDropZone } from "../ui/file-drop-zone";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { Sheet } from "../ui/sheet";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  isClassifiedApiError,
} from "../../lib/api";
import { apiFailureBanner } from "../../lib/failure-copy";
import {
  DECLARED_CATEGORIES,
  type DeclaredCategory,
} from "../../lib/attestation";
import styles from "./documents.module.css";

export type ImportSourceTab = "file" | "website";

export type ImportSourceSheetProps = {
  /** Close handler. */
  onClose: () => void;
  /** Active tab. */
  tab: ImportSourceTab;
  /** Tab change. */
  onTabChange: (tab: ImportSourceTab) => void;
  /** File tab convenience. */
  showUpload: boolean;
  /** Website tab convenience. */
  showCrawl: boolean;
  /** Selected file. */
  file: File | null;
  /** File picker. */
  onFile: (file: File | null) => void;
  /** Declared category. */
  category: DeclaredCategory;
  /** Category change. */
  onCategory: (category: DeclaredCategory) => void;
  /** Document title. */
  title: string;
  /** Title change. */
  onTitle: (title: string) => void;
  /** Attestation checkbox. */
  attested: boolean;
  /** Attestation change. */
  onAttested: (value: boolean) => void;
  /** Paid handshake gate. */
  allowPaidPost: boolean;
  /** Start reserve → storage → finalize. */
  onUpload: () => void;
  /** Client phase label. */
  uploadPhase: string | null;
  /** Success note. */
  uploadNote: string | null;
  /** Upload mutation error. */
  uploadError: Error | null;
  /** True while reserve/upload/finalize runs. */
  uploadPending: boolean;
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
 * Map an upload phase string to a status pill tone.
 *
 * @param phase - Client stage.
 * @returns Tone for Ready/Queued vs Failed.
 */
function uploadPhaseTone(phase: string): "neutral" | "success" | "warning" | "danger" {
  if (phase === "Failed") {
    return "danger";
  }
  if (phase === "Queued") {
    return "success";
  }
  if (phase === "Ready") {
    return "neutral";
  }
  return "warning";
}

/**
 * Render the import drawer. Tabs are omitted when the matching convenience
 * helper is false; hidden chrome is not authorization.
 *
 * @param props - Controlled import fields and existing mutations.
 * @returns Modal sheet. Does not call FastAPI.
 */
export function ImportSourceSheet({
  onClose,
  tab,
  onTabChange,
  showUpload,
  showCrawl,
  file,
  onFile,
  category,
  onCategory,
  title,
  onTitle,
  attested,
  onAttested,
  allowPaidPost,
  onUpload,
  uploadPhase,
  uploadNote,
  uploadError,
  uploadPending,
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
}: ImportSourceSheetProps) {
  const showFileTab = showUpload;
  const showWebsiteTab = showCrawl;
  const active: ImportSourceTab =
    tab === "website" && showWebsiteTab
      ? "website"
      : showFileTab
        ? "file"
        : "website";
  const stage = uploadPhase ?? (file ? "Ready" : null);
  return (
    <Sheet title="Import source" onClose={onClose}>
      <div className={styles.tabs}>
        {showFileTab ? (
          <Button
            type="button"
            variant={active === "file" ? "primary" : "secondary"}
            onClick={() => onTabChange("file")}
          >
            Files
          </Button>
        ) : null}
        {showWebsiteTab ? (
          <Button
            type="button"
            variant={active === "website" ? "primary" : "secondary"}
            onClick={() => onTabChange("website")}
          >
            Website
          </Button>
        ) : null}
      </div>
      {active === "file" && showFileTab ? (
        <div className={styles.formStack}>
          <FileDropZone
            onFiles={(files) => onFile(files[0] ?? null)}
            disabled={!allowPaidPost}
          />
          {file ? (
            <div className={styles.queueRow}>
              <div>
                <p>
                  <UserText value={file.name} />
                </p>
                <p className={styles.muted}>{String(file.size)} bytes</p>
              </div>
              {stage ? (
                <StatusPill status={stage} tone={uploadPhaseTone(stage)} />
              ) : null}
              {uploadPending ? null : (
                <Button type="button" variant="ghost" onClick={() => onFile(null)}>
                  Remove
                </Button>
              )}
            </div>
          ) : null}
          <Select
            label="Declared category"
            value={category}
            options={DECLARED_CATEGORIES.map((item) => ({
              value: item,
              label: item,
            }))}
            onChange={(event: ChangeEvent<HTMLSelectElement>) =>
              onCategory(event.target.value as DeclaredCategory)
            }
          />
          <Input
            label="Document title"
            value={title}
            onChange={(event) => onTitle(event.target.value)}
          />
          <label className={styles.checkLabel}>
            <input
              type="checkbox"
              checked={attested}
              onChange={(event) => onAttested(event.target.checked)}
            />{" "}
            I attest this source is allowed under the current processing policy.
          </label>
          <p className={styles.muted}>
            Uploads use your signed-in session. A reservation is never treated as
            ready for search.
          </p>
          <Button
            type="button"
            variant="primary"
            data-action-id="documents.upload"
            disabled={file === null || !allowPaidPost || !attested}
            pending={uploadPending}
            pendingLabel="Uploading…"
            onClick={onUpload}
          >
            Upload
          </Button>
          {uploadNote ? <p className={styles.muted}>{uploadNote}</p> : null}
          {uploadError ? (
            <StatusBanner kind="error" role="alert">
              {uploadError.message.startsWith("storage_upload_failed")
                ? "The file did not finish uploading. Try again after the storage write succeeds."
                : isClassifiedApiError(uploadError)
                  ? apiFailureBanner(uploadError.failure)
                  : "Upload rejected. Server authorization is authoritative."}
            </StatusBanner>
          ) : null}
        </div>
      ) : null}
      {active === "website" && showWebsiteTab ? (
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
      ) : null}
    </Sheet>
  );
}
