/**
 * Document detail: overview, processing, graph seed, tables. 404 has no title leak.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { ProcessingTimeline } from "./documents/processing-timeline";
import {
  INGESTION_STATUS_POLL_MS,
  ingestionStatusIsTerminal,
} from "./documents/ingestion-inspector";
import { ErrorState } from "./ui/error-state";
import { Skeleton } from "./ui/skeleton";
import { StatusPill } from "./ui/status-pill";
import { UserText } from "./ui/user-text";
import {
  fetchDocument,
  fetchMe,
  fetchVersionStatus,
  listTables,
  retryIngestionJob,
  type ApiAuth,
} from "../lib/api";
import { useSession } from "../lib/auth/session-provider";
import {
  DOCUMENT_DELETE_UNAVAILABLE,
  DOCUMENT_NOT_FOUND_COPY,
  SOURCE_PREVIEW_UNAVAILABLE,
} from "../lib/citation-drawer";
import { sessionQueryKeys } from "../lib/query-keys";
import styles from "./documents/documents.module.css";

/**
 * Authorized document detail. 404 renders "Not found" without a title.
 *
 * @param props - Route `documentId`.
 * @returns Detail surface.
 */
export function DocumentDetail({ documentId }: { documentId: string }) {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const [pageVisible, setPageVisible] = useState(true);

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

  return (
    <div className={styles.page}>
      <p className={styles.muted}>
        <Link href="/documents">Documents</Link>
      </p>
      <header className={styles.header}>
        <div>
          <h2>
            <UserText value={record.title ?? record.document_id} />
          </h2>
          <StatusPill status={record.visibility} />
        </div>
      </header>

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
        </dl>
      </section>

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

      <section className={styles.section} aria-label="Graph">
        <h2>Graph</h2>
        <p className={styles.muted}>
          Hop cap 3. This is a seed, not Graph Ready.
        </p>
        <Link href={`/graph?documentId=${encodeURIComponent(record.document_id)}`}>
          Inspect graph for this document
        </Link>
      </section>

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

      <p className={styles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
      <p className={styles.muted}>{DOCUMENT_DELETE_UNAVAILABLE}</p>
      <p className={styles.muted}>
        Signed in as <UserText value={meQuery.data?.role ?? ""} />. Role hiding
        is convenience only.
      </p>
    </div>
  );
}
