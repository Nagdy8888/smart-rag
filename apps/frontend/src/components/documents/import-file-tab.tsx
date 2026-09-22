/**
 * File import tab. Controlled fields only; parent owns reserve → finalize.
 */

import type { ChangeEvent } from "react";
import { Button } from "../ui/button";
import { FileDropZone } from "../ui/file-drop-zone";
import { Input } from "../ui/input";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import { isClassifiedApiError } from "../../lib/api";
import { apiFailureBanner } from "../../lib/failure-copy";
import { DECLARED_CATEGORIES, type DeclaredCategory } from "../../lib/attestation";
import styles from "./documents.module.css";
import { uploadImportErrorMessage } from "./hooks/use-document-library-import";

export type ImportFileTabProps = {
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
 * Render the Files tab. Does not call FastAPI.
 *
 * @param props - Controlled file import fields.
 * @returns File form. Handshake and attestation remain caller gates.
 */
export function ImportFileTab({
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
}: ImportFileTabProps) {
  const stage = uploadPhase ?? (file ? "Ready" : null);
  return (
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
          {uploadImportErrorMessage(uploadError) ??
            (uploadError.message.startsWith("storage_upload_failed")
              ? "The file did not finish uploading. Try again after the storage write succeeds."
              : isClassifiedApiError(uploadError)
                ? apiFailureBanner(uploadError.failure)
                : "Upload rejected. Server authorization is authoritative.")}
        </StatusBanner>
      ) : null}
    </div>
  );
}
