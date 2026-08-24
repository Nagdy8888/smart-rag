/**
 * Document detail: overview, processing, graph seed, tables. 404 has no title leak.
 */

"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ProcessingTimeline } from "./processing-timeline";
import {
  INGESTION_STATUS_POLL_MS,
  ingestionStatusIsTerminal,
} from "./ingestion-inspector";
import { Button } from "../ui/button";
import { ErrorState } from "../ui/error-state";
import { Icon } from "../ui/icon";
import { Menu } from "../ui/menu";
import { Sheet } from "../ui/sheet";
import { Skeleton } from "../ui/skeleton";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { UserText } from "../ui/user-text";
import {
  deleteDocument,
  fetchDocument,
  fetchMe,
  fetchVersionStatus,
  isClassifiedApiError,
  listTables,
  retryIngestionJob,
  type ApiAuth,
} from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { DOCUMENT_NOT_FOUND_COPY } from "../../lib/citation-drawer";
import { sessionQueryKeys } from "../../lib/query-keys";
import { isOwnerOrAdmin } from "../../lib/roles";
import styles from "./documents.module.css";

/**
 * Authorized document detail. 404 renders "Not found" without a title.
 *
 * @param props - Route `documentId`.
 * @returns Detail surface.
 */
export function DocumentDetail({ documentId }: { documentId: string }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [pageVisible, setPageVisible] = useState(true);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    function onVisibility(): void {
      setPageVisible(document.visibilityState === "visible");
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, []);

  const documentQuery = useQuery({
    queryKey: keys.document(documentId),
    queryFn: () => fetchDocument(auth as ApiAuth, documentId),
    enabled: auth !== null,
  });

  const versionId =
    documentQuery.data?.ok === true
      ? documentQuery.data.document.current_version_id
      : null;

  const versionQuery = useQuery({
    queryKey: keys.versionStatus(versionId),
    queryFn: () => fetchVersionStatus(auth as ApiAuth, versionId as string),
    enabled: auth !== null && versionId !== null,
    refetchInterval: (query) => {
      if (!pageVisible || versionId === null) {
        return false;
      }
      const status = query.state.data?.version?.status;
      if (!status || ingestionStatusIsTerminal(status)) {
        return false;
      }
      return INGESTION_STATUS_POLL_MS;
    },
  });

  const tablesQuery = useQuery({
    queryKey: keys.tables,
    queryFn: () => listTables(auth as ApiAuth),
    enabled: auth !== null,
  });

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const retryMutation = useMutation({
    mutationFn: (jobId: string) => retryIngestionJob(auth as ApiAuth, jobId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: keys.versionStatus(versionId),
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      await deleteDocument(auth, documentId);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: keys.documents });
      void queryClient.invalidateQueries({ queryKey: keys.document(documentId) });
      router.push("/documents?deleted=1");
    },
    onError: (error) => {
      if (isClassifiedApiError(error)) {
        if (error.failure.kind === "auth") {
          setDeleteError("You cannot delete this document.");
          return;
        }
        if (error.failure.kind === "deleted") {
          setDeleteOpen(false);
          router.push("/documents");
          return;
        }
        if (error.failure.kind === "rate") {
          setDeleteError("Too many attempts. Try later.");
          return;
        }
      }
      setDeleteError("Document could not be deleted.");
    },
  });

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  if (documentQuery.isPending) {
    return (
      <div className={styles.page}>
        <Skeleton label="Loading document" width="16rem" />
        <Skeleton label="Loading metadata" width="24rem" />
      </div>
    );
  }

  if (documentQuery.data?.ok === false || documentQuery.isError) {
    return (
      <div className={styles.page}>
        <ErrorState title="Not found" message={DOCUMENT_NOT_FOUND_COPY} />
      </div>
    );
  }

  const record =
    documentQuery.data?.ok === true ? documentQuery.data.document : null;
  if (record === null) {
    return (
      <div className={styles.page}>
        <ErrorState title="Not found" message={DOCUMENT_NOT_FOUND_COPY} />
      </div>
    );
  }

  const versionPayload = versionQuery.data;
  const tables = (tablesQuery.data ?? []).filter(
    (item) => item.document_id === record.document_id,
  );
  const canDelete = isOwnerOrAdmin(meQuery.data?.role);
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
          <StatusPill status={record.visibility} />
          {versionPayload ? (
            <StatusPill status={statusLabel} />
          ) : null}
        </div>
        {canDelete ? (
          <Menu
            label="Document actions"
            trigger={<Icon name="more" />}
            items={[
              {
                id: "delete",
                label: "Delete",
                danger: true,
                actionId: "documents.delete",
                onSelect: () => {
                  setDeleteError(null);
                  setDeleteOpen(true);
                },
              },
            ]}
          />
        ) : null}
      </header>

      <div className={styles.detailGrid}>
        <div>
          {versionPayload ? (
            <ProcessingTimeline
              payload={versionPayload}
              onRetry={(jobId) => retryMutation.mutate(jobId)}
            />
          ) : (
            <section className={styles.section} aria-label="Processing">
              <h2>Processing</h2>
              <p className={styles.muted}>No current version to inspect.</p>
            </section>
          )}

          <section className={styles.section} aria-label="Tables">
            <h2>Tables</h2>
            {tables.length === 0 ? (
              <p className={styles.muted}>No authorized tables on this document.</p>
            ) : (
              <ul className={styles.jobList}>
                {tables.map((table) => (
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
            Signed in as <UserText value={meQuery.data?.role ?? ""} />. Role hiding
            is convenience only.
          </p>
        </aside>
      </div>

      {deleteOpen ? (
        <Sheet
          title="Delete document?"
          onClose={() => {
            setDeleteOpen(false);
            setDeleteError(null);
          }}
        >
          <p className={styles.confirmBody}>
            “<UserText value={record.title ?? record.document_id} />” will be
            removed from retrieval and scheduled for cleanup. This cannot be
            undone.
          </p>
          {deleteError ? (
            <StatusBanner kind="error" role="alert">
              {deleteError}
            </StatusBanner>
          ) : null}
          <div className={styles.toolbar}>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDeleteOpen(false);
                setDeleteError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant="danger"
              data-action-id="documents.delete"
              pending={deleteMutation.isPending}
              pendingLabel="Deleting…"
              onClick={() => deleteMutation.mutate()}
            >
              Delete document
            </Button>
          </div>
        </Sheet>
      ) : null}
    </div>
  );
}
