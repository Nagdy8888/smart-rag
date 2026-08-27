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
import { absentStatusLabel, formatVisibility } from "../../lib/format-visibility";
import { compactIngestionPills } from "../../lib/ingestion-status";
import { formatRelativeTime } from "../../lib/relative-time";
import type {
  DocumentIngestionStatusResponse,
  DocumentResponse,
} from "../../lib/types";
import styles from "./documents.module.css";

export type DocumentListProps = {
  /** Already loaded documents (possibly several keyset pages). */
  documents: DocumentResponse[];
  /** Version status keyed by `current_version_id`. */
  statusByVersionId?: Record<string, DocumentIngestionStatusResponse>;
  /** Version ids whose status request is still in flight. */
  pendingStatusIds?: ReadonlySet<string>;
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
      label: "View processing",
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
 * Return search and graph status nodes for one document.
 *
 * @param doc - List row.
 * @param statusByVersionId - Fetched envelopes.
 * @param pendingStatusIds - In-flight version ids.
 * @returns Two display nodes.
 */
function statusDisplays(
  doc: DocumentResponse,
  statusByVersionId: Record<string, DocumentIngestionStatusResponse>,
  pendingStatusIds: ReadonlySet<string>,
): { search: ReactNode; graph: ReactNode } {
  const versionId = doc.current_version_id;
  if (!versionId) {
    return {
      search: absentStatusLabel("index"),
      graph: absentStatusLabel("index"),
    };
  }
  if (pendingStatusIds.has(versionId)) {
    return {
      search: <span className={styles.muted}>Loading…</span>,
      graph: <span className={styles.muted}>Loading…</span>,
    };
  }
  const payload = statusByVersionId[versionId];
  if (payload === undefined) {
    return {
      search: absentStatusLabel("index"),
      graph: absentStatusLabel("index"),
    };
  }
  const pills = compactIngestionPills(payload.version.status);
  return {
    search: pills.search ? (
      <StatusPill status={pills.search.label} tone={pills.search.tone} />
    ) : (
      absentStatusLabel("pending")
    ),
    graph: pills.graph ? (
      <StatusPill status={pills.graph.label} tone={pills.graph.tone} />
    ) : (
      absentStatusLabel("pending")
    ),
  };
}

/**
 * Render the document name and optional id fallback.
 *
 * @param doc - List row.
 * @returns Name block.
 */
function DocumentName({ doc }: { doc: DocumentResponse }) {
  return (
    <div>
      <span className={styles.nameCell}>
        <span className={styles.docIcon} aria-hidden="true">
          <Icon name="documents" />
        </span>
        <Link href={`/documents/${doc.document_id}`} className={styles.nameLink}>
          <UserText value={doc.title ?? doc.document_id} />
        </Link>
      </span>
      {doc.title ? null : (
        <p className={styles.mono}>
          <UserText value={doc.document_id} />
        </p>
      )}
    </div>
  );
}

/**
 * Render a created timestamp, or an em dash.
 *
 * @param createdAt - ISO timestamp.
 * @returns Time node.
 */
function CreatedAt({ createdAt }: { createdAt: string | null }) {
  if (!createdAt) {
    return "—";
  }
  const absolute = new Date(createdAt).toLocaleString();
  return (
    <time dateTime={createdAt} title={absolute}>
      {formatRelativeTime(createdAt)}
    </time>
  );
}

/**
 * Render name, visibility, created time, and row actions.
 *
 * Search/graph cells use loaded version status. Row clicks do not navigate;
 * only the name link does.
 *
 * @param props - Documents and action callbacks.
 * @returns Table, mobile cards, or empty state.
 */
export function DocumentList({
  documents,
  statusByVersionId = {},
  pendingStatusIds = new Set(),
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
      <EmptyState
        icon="documents"
        title={emptyTitle}
        body={emptyBody}
        action={emptyAction}
      />
    );
  }
  return (
    <>
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <caption className={styles.tableCaption}>Authorized documents</caption>
          <thead>
            <tr>
              <th scope="col">Name</th>
              <th scope="col">Visibility</th>
              <th scope="col">Search status</th>
              <th scope="col">Graph status</th>
              <th scope="col">Created</th>
              <th scope="col">
                <span className={styles.srOnly}>Actions</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {documents.map((doc) => {
              const status = statusDisplays(doc, statusByVersionId, pendingStatusIds);
              return (
                <tr key={doc.document_id}>
                  <td>
                    <DocumentName doc={doc} />
                  </td>
                  <td>
                    <StatusPill status={formatVisibility(doc.visibility)} />
                  </td>
                  <td>{status.search}</td>
                  <td>{status.graph}</td>
                  <td className={styles.metaCell}>
                    <CreatedAt createdAt={doc.created_at} />
                  </td>
                  <td className={styles.actionsCell}>
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
              );
            })}
          </tbody>
        </table>
      </div>
      <ul className={styles.mobileList}>
        {documents.map((doc) => {
          const status = statusDisplays(doc, statusByVersionId, pendingStatusIds);
          return (
            <li key={doc.document_id} className={styles.mobileCard}>
              <DocumentName doc={doc} />
              <div className={styles.mobilePills}>
                {status.search}
                {status.graph}
              </div>
              <p className={styles.mobileMeta}>
                {formatVisibility(doc.visibility)}
                {doc.created_at ? (
                  <>
                    {" · "}
                    <CreatedAt createdAt={doc.created_at} />
                  </>
                ) : null}
              </p>
              <div className={styles.mobileActions}>
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
              </div>
            </li>
          );
        })}
      </ul>
    </>
  );
}

/**
 * Primary empty-state action label for the library header.
 */
export const IMPORT_SOURCE_LABEL = "Import source";
