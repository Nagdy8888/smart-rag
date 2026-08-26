/**
 * Document detail: overview, processing, graph seed, tables. 404 has no title leak.
 */

"use client";

import Link from "next/link";
import { IngestionStatus } from "./ingestion-status";
import { DocumentDeleteSheet } from "./document-delete-sheet";
import { useDocumentDetail } from "./hooks/use-document-detail";
import { ErrorState } from "../ui/error-state";
import { Icon } from "../ui/icon";
import { Menu } from "../ui/menu";
import { Skeleton } from "../ui/skeleton";
import { StatusPill } from "../ui/status-pill";
import { formatVisibility } from "../../lib/format-visibility";
import { UserText } from "../ui/user-text";
import { DOCUMENT_NOT_FOUND_COPY } from "../../lib/citation-drawer";
import styles from "./documents.module.css";

/**
 * Authorized document detail. 404 renders "Not found" without a title.
 *
 * @param props - Route `documentId`.
 * @returns Detail surface.
 */
export function DocumentDetail({ documentId }: { documentId: string }) {
  const detail = useDocumentDetail(documentId);

  if (!detail.signedIn) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  if (detail.pending) {
    return (
      <div className={styles.page}>
        <Skeleton label="Loading document" width="16rem" />
        <Skeleton label="Loading metadata" width="24rem" />
      </div>
    );
  }

  if (detail.missing || detail.record === null) {
    return (
      <div className={styles.page}>
        <ErrorState title="Not found" message={DOCUMENT_NOT_FOUND_COPY} />
      </div>
    );
  }

  const record = detail.record;
  const versionPayload = detail.versionPayload;
  const statusLabel = versionPayload?.version.status ?? record.visibility;

  return (
    <div className={styles.page}>
      <p className={styles.muted}>
        <Link href="/documents">Documents</Link>
      </p>
      <header className={styles.header}>
        <div>
          <h1>
            <UserText value={record.title ?? record.document_id} />
          </h1>
          <StatusPill status={formatVisibility(record.visibility)} />
          {versionPayload ? <StatusPill status={statusLabel} /> : null}
        </div>
        {detail.canDelete ? (
          <Menu
            label="Document actions"
            trigger={<Icon name="more" />}
            items={[
              {
                id: "delete",
                label: "Delete",
                danger: true,
                actionId: "documents.delete",
                onSelect: detail.openDelete,
              },
            ]}
          />
        ) : null}
      </header>

      <div className={styles.detailGrid}>
        <div>
          {versionPayload ? (
            <IngestionStatus
              payload={versionPayload}
              layout="timeline"
              onRetry={detail.retryJob}
              retryPending={detail.retryPending}
            />
          ) : (
            <section className={styles.section} aria-label="Processing">
              <h2>Processing</h2>
              <p className={styles.muted}>No current version to inspect.</p>
            </section>
          )}

          <section className={styles.section} aria-label="Tables">
            <h2>Tables</h2>
            {detail.tables.length === 0 ? (
              <p className={styles.muted}>No authorized tables on this document.</p>
            ) : (
              <ul className={styles.jobList}>
                {detail.tables.map((table) => (
                  <li key={table.table_id}>
                    <Link href="/tables">
                      <UserText value={table.table_name} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>

        <aside>
          <section className={styles.section} aria-label="Overview">
            <h2>Overview</h2>
            <dl className={styles.dl}>
              <dt>Document</dt>
              <dd className={styles.mono}>
                <UserText value={record.document_id} />
              </dd>
              <dt>Current version</dt>
              <dd className={styles.mono}>
                <UserText value={record.current_version_id ?? "none"} />
              </dd>
              <dt>Created</dt>
              <dd>
                {record.created_at
                  ? new Date(record.created_at).toLocaleString()
                  : "—"}
              </dd>
            </dl>
          </section>
          <div className={styles.sideActions}>
            <Link href={`/graph?documentId=${encodeURIComponent(record.document_id)}`}>
              Inspect in graph
            </Link>
            <Link href={`/tables?documentId=${encodeURIComponent(record.document_id)}`}>
              Open tables
            </Link>
          </div>
          <p className={styles.muted}>
            Signed in as <UserText value={detail.roleLabel} />. Role hiding
            is convenience only.
          </p>
        </aside>
      </div>

      {detail.deleteOpen ? (
        <DocumentDeleteSheet
          label={record.title ?? record.document_id}
          deleteError={detail.deleteError}
          pending={detail.deletePending}
          onClose={detail.closeDelete}
          onConfirm={detail.confirmDelete}
        />
      ) : null}
    </div>
  );
}
