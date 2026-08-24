/**
 * Import source sheet: File and Website tabs gated by role convenience helpers.
 */

import type { ChangeEvent } from "react";
import { Button } from "../ui/button";
import { FileDropZone } from "../ui/file-drop-zone";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { Sheet } from "../ui/sheet";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import { MFA_UPLOAD_DENIED } from "../../lib/auth/copy";
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
  /** Crawl start URL. */
  startUrl: string;
  /** Start URL change. */
  onStartUrl: (value: string) => void;
  /** Approved domain. */
  approvedDomain: string;
  /** Domain change. */
  onApprovedDomain: (value: string) => void;
  /** Enqueue crawl. */
  onCrawl: () => void;
  /** Crawl mutation error. */
  crawlError: boolean;
};

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
  allowPaidPost,
  onUpload,
  uploadPhase,
  uploadNote,
  uploadError,
  startUrl,
  onStartUrl,
  approvedDomain,
  onApprovedDomain,
  onCrawl,
  crawlError,
}: ImportSourceSheetProps) {
  const showFileTab = showUpload;
  const showWebsiteTab = showCrawl;
  const active: ImportSourceTab =
    tab === "website" && showWebsiteTab
      ? "website"
      : showFileTab
        ? "file"
        : "website";
  return (
    <Sheet title="Import source" onClose={onClose}>
      <div className={styles.tabs}>
        {showFileTab ? (
          <Button
            type="button"
            variant={active === "file" ? "primary" : "secondary"}
            onClick={() => onTabChange("file")}
          >
            File
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
            <p className={styles.muted}>
              <UserText value={file.name} /> — {String(file.size)} bytes
            </p>
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
          <p className={styles.muted}>
            Category and attestation are recorded with the upload. Files are not
            searchable until ingestion completes.
          </p>
          <Input
            label="Document title"
            value={title}
            onChange={(event) => onTitle(event.target.value)}
          />
          <p className={styles.muted}>
            Uploads use your signed-in session. A reservation is never treated as
            ready for search.
          </p>
          <Button
            type="button"
            variant="primary"
            disabled={file === null || !allowPaidPost}
            onClick={onUpload}
          >
            Reserve, upload, finalize
          </Button>
          {uploadPhase ? <p className={styles.phase}>{uploadPhase}</p> : null}
          {uploadNote ? <p className={styles.muted}>{uploadNote}</p> : null}
          {uploadError ? (
            <StatusBanner kind="error" role="alert">
              {uploadError.message === "mfa_required"
                ? MFA_UPLOAD_DENIED
                : uploadError.message.startsWith("storage_upload_failed")
                  ? "The file did not finish uploading. Try again after the storage write succeeds."
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
          <Button
            type="button"
            disabled={!allowPaidPost || startUrl.trim() === ""}
            onClick={onCrawl}
          >
            Enqueue crawl
          </Button>
          {crawlError ? (
            <StatusBanner kind="error" role="alert">
              Crawl rejected. Members receive HTTP 403 from the server.
            </StatusBanner>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  );
}
