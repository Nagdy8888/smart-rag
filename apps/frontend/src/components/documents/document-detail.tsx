/**
 * Document detail: overview, processing, graph seed, tables. 404 has no title leak.
 */

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IngestionStatus } from "./ingestion-status";
import { DocumentDeleteSheet } from "./document-delete-sheet";
import { useDocumentDetail } from "./hooks/use-document-detail";
import { Button } from "../ui/button";
import { ErrorState } from "../ui/error-state";
import { Icon } from "../ui/icon";
import { Menu } from "../ui/menu";
import { Skeleton } from "../ui/skeleton";
import { StatusPill } from "../ui/status-pill";
import { formatVisibility } from "../../lib/format-visibility";
import { compactIngestionPills } from "../../lib/ingestion-status";
import { formatRelativeTime } from "../../lib/relative-time";
import { CodeText, UserText } from "../ui/user-text";
import { DOCUMENT_NOT_FOUND_COPY } from "../../lib/citation-drawer";
import {
  EMPTY_DOCUMENT_TABLES_COPY,
  tablesWorkspaceHref,
} from "../../lib/table-plan";
import styles from "./documents.module.css";

/**
 * Copy a visible identifier. Missing clipboard support is a visible failure.
 *
 * @param props - Exact id string already shown in monospace.
 * @returns Compact control.
 */
function CopyIdButton({ value }: { value: string }) {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") {
      return;
    }
    const timer = window.setTimeout(() => {
      setState("idle");
    }, 2000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [state]);

  return (
    <Button
      type="button"
      variant="ghost"
      size="compact"
      aria-label={`Copy ${value}`}
      onClick={() => {
        void (async () => {
          if (navigator.clipboard?.writeText === undefined) {
            setState("failed");
            return;
          }
          try {
            await navigator.clipboard.writeText(value);
            setState("copied");
          } catch {
            setState("failed");
          }
        })();
      }}
    >
      {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}
    </Button>
  );
}

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
  const versionStatus = versionPayload?.version.status;
  const statusPills = versionStatus ? compactIngestionPills(versionStatus) : null;
  const createdLabel = record.created_at
    ? formatRelativeTime(record.created_at)
    : null;

  return (
    <div className={styles.page}>
      <p className={styles.backLink}>
        <Link href="/documents">Back to documents</Link>
      </p>
      <header className={styles.header}>
        <div>
          <h1>
            <UserText value={record.title ?? record.document_id} />
          </h1>
          <div className={styles.headerPills}>
            <StatusPill status={formatVisibility(record.visibility)} />
            {statusPills?.search ? (
              <StatusPill
                status={statusPills.search.label}
                tone={statusPills.search.tone}
              />
            ) : null}
            {statusPills?.graph ? (
              <StatusPill
                status={statusPills.graph.label}
                tone={statusPills.graph.tone}
              />
            ) : null}
          </div>
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
          <section className={styles.section} aria-label="Processing">
            <h2>Processing</h2>
            {versionPayload ? (
              <IngestionStatus
                payload={versionPayload}
                layout="timeline"
                onRetry={detail.retryJob}
                retryPending={detail.retryPending}
              />
            ) : (
              <p className={styles.muted}>
                {record.current_version_id
                  ? detail.versionPending
                    ? "Loading…"
                    : "Processing details could not be loaded."
                  : "No current version to inspect."}
              </p>
            )}
          </section>

          <section className={styles.section} aria-label="Tables">
            <h2>Tables</h2>
            {detail.tables.length === 0 ? (
              <p className={styles.muted}>{EMPTY_DOCUMENT_TABLES_COPY}</p>
            ) : (
              <ul className={styles.jobList}>
                {detail.tables.map((table) => (
                  <li key={table.table_id}>
                    <Link
                      href={tablesWorkspaceHref({
                        tableId: table.table_id,
                        documentId: record.document_id,
                      })}
                    >
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
              <dd className={styles.idRow}>
                <CodeText value={record.document_id} />
                <CopyIdButton value={record.document_id} />
              </dd>
              {record.current_version_id ? (
                <>
                  <dt>Current version</dt>
                  <dd className={styles.idRow}>
                    <CodeText value={record.current_version_id} />
                    <CopyIdButton value={record.current_version_id} />
                  </dd>
                </>
              ) : null}
              {record.created_at && createdLabel ? (
                <>
                  <dt>Created</dt>
                  <dd>
                    <time
                      dateTime={record.created_at}
                      title={new Date(record.created_at).toLocaleString()}
                    >
                      {createdLabel}
                    </time>
                  </dd>
                </>
              ) : null}
            </dl>
          </section>
          <div className={styles.sideActions}>
            <Link href={`/graph?documentId=${encodeURIComponent(record.document_id)}`}>
              Inspect in graph
            </Link>
            <Link
              href={tablesWorkspaceHref({ documentId: record.document_id })}
            >
              Open tables
            </Link>
          </div>
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
