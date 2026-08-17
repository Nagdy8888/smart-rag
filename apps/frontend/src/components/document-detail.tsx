/**
 * Document detail: metadata, ingestion status, graph inspect seed, tables list.
 * No audit/PII/source-preview tabs (GAP-07-09/12). 404 has no title leak.
 */

"use client";

import Link from "next/link";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { Button } from "./ui/button";
import { ErrorState } from "./ui/error-state";
import { LimitationCallout } from "./ui/limitation-callout";
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
import {
  formatBm25Summary,
  formatGraphHandoffSummary,
  ingestionStatusLabel,
  ingestionStatusTone,
} from "../lib/ingestion-status";
import { graphNotReadyCopy, limitationCopy } from "../lib/limitations";
import { sessionQueryKeys } from "../lib/query-keys";
import styles from "./developer-app.module.css";

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
      <div className={styles.shell}>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  if (documentQuery.isPending) {
    return (
      <div className={styles.shell}>
        <p className={styles.muted}>Loading</p>
      </div>
    );
  }

  if (documentQuery.data?.ok === false || documentQuery.isError) {
    return (
      <div className={styles.shell}>
        <ErrorState title="Not found" message={DOCUMENT_NOT_FOUND_COPY} />
      </div>
    );
  }

  const document =
    documentQuery.data?.ok === true ? documentQuery.data.document : null;
  if (document === null) {
    return (
      <div className={styles.shell}>
        <ErrorState title="Not found" message={DOCUMENT_NOT_FOUND_COPY} />
      </div>
    );
  }

  const version = versionQuery.data?.version ?? null;
  const tables = (tablesQuery.data ?? []).filter(
    (item) => item.document_id === document.document_id,
  );
  const retryAllowed = version?.retry_allowed === true;

  return (
    <div className={styles.shell}>
      <p className={styles.muted}>
        <Link href="/documents">Documents</Link>
      </p>
      <h1>
        <UserText value={document.title ?? document.document_id} />
      </h1>
      <StatusPill status={document.visibility} />
      <dl>
        <dt>document_id</dt>
        <dd>
          <UserText value={document.document_id} />
        </dd>
        <dt>current_version_id</dt>
        <dd>
          <UserText value={document.current_version_id ?? "none"} />
        </dd>
      </dl>
      {version ? (
        <section className={styles.panel} aria-label="Ingestion status">
          <h2>Ingestion status</h2>
          <StatusPill
            status={ingestionStatusLabel(version.status)}
            tone={ingestionStatusTone(version.status)}
          />
          <dl>
            <dt>BM25</dt>
            <dd>{formatBm25Summary(version.bm25)}</dd>
            <dt>Graph handoff</dt>
            <dd>{formatGraphHandoffSummary(version.graph_handoff)}</dd>
          </dl>
          {version.status === "graph_pending" ? (
            <LimitationCallout tone="warning">
              {limitationCopy("graph_pending")} {graphNotReadyCopy(1)}
            </LimitationCallout>
          ) : null}
          {version.status === "deletion_pending" ? (
            <StatusPill status="deletion_pending" tone="warning" />
          ) : null}
          <ul className={styles.list}>
            {(versionQuery.data?.recent_jobs ?? []).map((job) => (
              <li key={job.id}>
                <UserText value={job.job_kind} /> —{" "}
                <UserText value={job.status} />
                {retryAllowed ? (
                  <Button
                    type="button"
                    onClick={() => retryMutation.mutate(job.id)}
                  >
                    Retry
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className={styles.panel} aria-label="Graph inspect seed">
        <h2>Graph inspect seed</h2>
        <p className={styles.muted}>
          Hop cap 3. This is a seed, not Graph Ready.
        </p>
        <Link href={`/graph?documentId=${encodeURIComponent(document.document_id)}`}>
          Inspect graph for this document
        </Link>
      </section>

      <section className={styles.panel} aria-label="Tables">
        <h2>Tables</h2>
        {tables.length === 0 ? (
          <p className={styles.muted}>No authorized tables on this document.</p>
        ) : (
          <ul className={styles.list}>
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
