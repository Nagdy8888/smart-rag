/**
 * Shared delete confirmation for library rows and document detail.
 */

import { Button } from "../ui/button";
import { Sheet } from "../ui/sheet";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import { isClassifiedApiError } from "../../lib/api";
import styles from "./documents.module.css";

export type DocumentDeleteSheetProps = {
  /** Title or document id shown in the confirmation sentence. */
  label: string;
  /** Classified delete failure, or null. */
  deleteError: string | null;
  /** True while DELETE is in flight. */
  pending: boolean;
  /** Close without deleting. */
  onClose: () => void;
  /** Confirm DELETE. Caller owns the mutation. */
  onConfirm: () => void;
};

export type DocumentDeleteFailureKind = "auth" | "deleted" | "rate" | "generic";

/**
 * Classify a document DELETE failure for confirmation chrome.
 *
 * @param error - Mutation error.
 * @returns Failure kind. Authorization remains on the server.
 */
export function classifyDocumentDeleteFailure(
  error: unknown,
): DocumentDeleteFailureKind {
  if (isClassifiedApiError(error)) {
    if (error.failure.kind === "auth") {
      return "auth";
    }
    if (error.failure.kind === "deleted") {
      return "deleted";
    }
    if (error.failure.kind === "rate") {
      return "rate";
    }
  }
  return "generic";
}

/**
 * English copy for a library-row delete failure.
 *
 * @param kind - Classified kind.
 * @returns Banner text. Detail 404 stays on the row, not this helper.
 */
export function documentDeleteFailureCopy(kind: DocumentDeleteFailureKind): string {
  if (kind === "auth") {
    return "You cannot delete this document.";
  }
  if (kind === "deleted") {
    return "Document not found.";
  }
  if (kind === "rate") {
    return "Too many attempts. Try later.";
  }
  return "Document could not be deleted.";
}

/**
 * Confirm document deletion. Does not call FastAPI.
 *
 * @param props - Label, error, and confirm/close handlers.
 * @returns Modal sheet.
 */
export function DocumentDeleteSheet({
  label,
  deleteError,
  pending,
  onClose,
  onConfirm,
}: DocumentDeleteSheetProps) {
  return (
    <Sheet title="Delete document?" onClose={onClose}>
      <p className={styles.confirmBody}>
        “<UserText value={label} />” will be removed from retrieval and scheduled
        for cleanup. This cannot be undone.
      </p>
      {deleteError ? (
        <StatusBanner kind="error" role="alert">
          {deleteError}
        </StatusBanner>
      ) : null}
      <div className={styles.toolbar}>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancel
        </Button>
        <Button
          type="button"
          variant="danger"
          data-action-id="documents.delete"
          pending={pending}
          pendingLabel="Deleting…"
          onClick={onConfirm}
        >
          Delete document
        </Button>
      </div>
    </Sheet>
  );
}
