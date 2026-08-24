/**
 * Loaded-document table. Parent owns fetch, filter, and mutations.
 */

import type { ReactNode } from "react";
import Link from "next/link";
import { EmptyState } from "../ui/empty-state";
import { Icon } from "../ui/icon";
import { Menu, type MenuItem } from "../ui/menu";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import { compactIngestionPills } from "../../lib/ingestion-status";
import type {
  DocumentIngestionStatusResponse,
  DocumentResponse,
} from "../../lib/types";
import styles from "./documents.module.css";

export type DocumentListProps = {
  /** Already loaded documents (possibly several keyset pages). */
  documents: DocumentResponse[];
  /** Version status keyed by `current_version_id` after Load status. */
  statusByVersionId?: Record<string, DocumentIngestionStatusResponse>;
  /** Open the version status inspector. */
  onLoadStatus: (versionId: string) => void;
  /** App-router navigation to the detail page. */
  onViewDetails: (documentId: string) => void;
  /** Owner/admin convenience. Server still authorizes DELETE. */
  canDelete?: boolean;
  /** Request delete confirmation for one row. */
  onDelete?: (document: DocumentResponse) => void;
  /** Empty-state primary action when import is allowed. */
  emptyAction?: ReactNode;
  /** Override empty heading when a local filter matches nothing. */
  emptyTitle?: string;
  /** Override empty body. */
  emptyBody?: string;
};

/**
 * Build overflow items for one row. Row clicks do not navigate.
 *
 * @param doc - List row.
 * @param onLoadStatus - Open status for `current_version_id`.
 * @param onViewDetails - Navigate to detail.
 * @param canDelete - Convenience flag.
 * @param onDelete - Open delete confirmation.
 * @returns Menu items.
 */
function rowMenuItems(
  doc: DocumentResponse,
  onLoadStatus: (versionId: string) => void,
  onViewDetails: (documentId: string) => void,
  canDelete: boolean,
  onDelete: ((document: DocumentResponse) => void) | undefined,
): MenuItem[] {
  const items: MenuItem[] = [
    {
      id: "details",
      label: "View details",
      actionId: "documents.view",
      onSelect: () => {
        onViewDetails(doc.document_id);
      },
    },
  ];
  if (doc.current_version_id) {
    items.push({
      id: "status",
      label: "Load status",
      actionId: "documents.status",
      onSelect: () => {
        onLoadStatus(doc.current_version_id as string);
      },
    });
  }
  if (canDelete && onDelete) {
    items.push({
      id: "delete",
      label: "Delete",
      danger: true,
      actionId: "documents.delete",
      onSelect: () => {
        onDelete(doc);
      },
    });
  }
  return items;
}

/**
 * Render search/graph cells from loaded version status only.
 *
 * @param doc - List row.
 * @param statusByVersionId - Fetched envelopes.
 * @returns Two table cells.
 */
function StatusCells({
  doc,
  statusByVersionId,
}: {
  doc: DocumentResponse;
  statusByVersionId: Record<string, DocumentIngestionStatusResponse>;
}) {
  const versionId = doc.current_version_id;
  const payload = versionId ? statusByVersionId[versionId] : undefined;
  if (payload === undefined) {
    return (
      <>
        <td>—</td>
        <td>—</td>
      </>
    );
  }
  const pills = compactIngestionPills(payload.version.status);
  return (
    <>
      <td>
        {pills.search ? (
          <StatusPill status={pills.search.label} tone={pills.search.tone} />
        ) : (
          "—"
        )}
      </td>
      <td>
        {pills.graph ? (
          <StatusPill status={pills.graph.label} tone={pills.graph.tone} />
        ) : (
          "—"
        )}
      </td>
    </>
  );
}

/**
 * Render name, visibility, created time, and row actions.
 *
 * Search/graph cells stay em dash until version status is loaded.
 * Row clicks do not navigate; only the name link does.
 *
 * @param props - Documents and action callbacks.
 * @returns Table, mobile cards, or empty state.
 */
export function DocumentList({
  documents,
  statusByVersionId = {},
  onLoadStatus,
  onViewDetails,
  canDelete = false,
  onDelete,
  emptyAction,
  emptyTitle = "No documents yet.",
  emptyBody = "Import a file or approved website to create searchable company knowledge.",
}: DocumentListProps) {
  if (documents.length === 0) {
    return (
      <EmptyState title={emptyTitle}>
        <p>{emptyBody}</p>
        {emptyAction}
      </EmptyState>
    );
  }
  return (
    <>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className={styles.muted}>
            Authorized documents already loaded. Filter does not search the server.
          </caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Visibility</th>
              <th scope="col">Search status</th>
              <th scope="col">Graph status</th>
              <th scope="col">Created</th>
              <th scope="col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => (
              <tr key={doc.document_id}>
                <td>
                  <span className={styles.nameCell}>
                    <Icon name="documents" aria-hidden="true" />
                    <Link href={`/documents/${doc.document_id}`}>
                      <UserText value={doc.title ?? doc.document_id} />
                    </Link>
                  </span>
                  {doc.title ? null : (
                    <p className={styles.mono}>
                      <UserText value={doc.document_id} />
                    </p>
                  )}
                </td>
                <td>
                  <StatusPill status={doc.visibility} />
                </td>
                <StatusCells doc={doc} statusByVersionId={statusByVersionId} />
                <td>
                  {doc.created_at
                    ? new Date(doc.created_at).toLocaleString()
                    : "—"}
                </td>
                <td>
                  <Menu
                    label="Document actions"
                    trigger={<Icon name="more" />}
                    items={rowMenuItems(
                      doc,
                      onLoadStatus,
                      onViewDetails,
                      canDelete,
                      onDelete,
                    )}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

/**
 * Primary empty-state action label for the library header.
 */
export const IMPORT_SOURCE_LABEL = "Import source";
