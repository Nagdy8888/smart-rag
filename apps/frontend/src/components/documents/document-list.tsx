/**
 * Loaded-document table. Filter is applied by the parent over already fetched rows.
 */

import Link from "next/link";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import type { DocumentResponse } from "../../lib/types";
import styles from "./documents.module.css";

export type DocumentListProps = {
  /** Already loaded documents (one API page). */
  documents: DocumentResponse[];
  /** Open the version status inspector. */
  onLoadStatus: (versionId: string) => void;
};

/**
 * Render title, visibility, current version, and Load status.
 *
 * @param props - Documents and status callback.
 * @returns Table or empty state. Row click is not a fetch.
 */
export function DocumentList({ documents, onLoadStatus }: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <EmptyState title="No documents you can see">
        Upload a file or wait for an invitation that grants access.
      </EmptyState>
    );
  }
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <caption className={styles.muted}>Authorized documents on this page</caption>
        <thead>
          <tr>
            <th scope="col">Title</th>
            <th scope="col">Visibility</th>
            <th scope="col">Version</th>
            <th scope="col">Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.document_id}>
              <td>
                <Link href={`/documents/${doc.document_id}`}>
                  <UserText value={doc.title ?? doc.document_id} />
                </Link>
              </td>
              <td>
                <StatusPill status={doc.visibility} />
              </td>
              <td className={styles.mono}>
                <UserText value={doc.current_version_id ?? "none"} />
              </td>
              <td>
                {doc.current_version_id ? (
                  <Button
                    type="button"
                    onClick={() => onLoadStatus(doc.current_version_id as string)}
                  >
                    Load status
                  </Button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
