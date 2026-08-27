/**
 * Structured tables: authorized manifests, guided TableQueryPlan, deterministic rows.
 * No SQL textarea. No client-summed totals. No Export, Save, or Share.
 */

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { AnalysisPlan } from "./analysis-plan";
import { AnalysisResults } from "./analysis-results";
import { TablesDocumentBar } from "./tables-document-bar";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { PageHeader } from "../ui/page-header";
import { Select } from "../ui/select";
import { Skeleton } from "../ui/skeleton";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import {
  analyzeTable,
  fetchDocument,
  isClassifiedApiError,
  listTables,
  type ApiAuth,
} from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import { apiFailureBanner, GENERIC_PRODUCTION_ERROR } from "../../lib/failure-copy";
import { sessionQueryKeys } from "../../lib/query-keys";
import {
  EMPTY_MANIFESTS_COPY,
  EMPTY_TABLE_PLAN_DRAFT,
  compileTablePlanDraft,
  documentDisplayName,
  manifestsForDocument,
  resolveSelectedManifest,
  tableDocumentIds,
  tablePlanCompileCopy,
  type TablePlanDraft,
} from "../../lib/table-plan";
import type { TableQueryPlan } from "../../lib/types";
import styles from "./tables.module.css";

/**
 * Tables list and analyze surface.
 *
 * @returns Tables UI.
 */
export function TablesApp() {
  const session = useSession();
  const searchParams = useSearchParams();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const tableIdParam = searchParams.get("tableId");
  const documentIdParam = searchParams.get("documentId");
  const scopedToDocument =
    documentIdParam !== null && documentIdParam !== "";
  const [userSelectedId, setUserSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<TablePlanDraft>(EMPTY_TABLE_PLAN_DRAFT);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [submittedPlan, setSubmittedPlan] = useState<TableQueryPlan | null>(null);
  const [displaySortKey, setDisplaySortKey] = useState<string | null>(null);
  const [displaySortDir, setDisplaySortDir] = useState<"asc" | "desc">("asc");

  useEffect(() => {
    setUserSelectedId(null);
  }, [documentIdParam]);

  const tablesQuery = useQuery({
    queryKey: keys.tables,
    queryFn: () => listTables(auth as ApiAuth),
    enabled: auth !== null,
  });

  const manifests = tablesQuery.data ?? [];
  const visibleManifests = manifestsForDocument(manifests, documentIdParam);
  const selected = resolveSelectedManifest(
    visibleManifests,
    userSelectedId,
    tableIdParam,
    documentIdParam,
  );
  const documentIds = tableDocumentIds(manifests, documentIdParam);
  const documentQueries = useQueries({
    queries: documentIds.map((documentId) => ({
      queryKey: keys.document(documentId),
      queryFn: () => fetchDocument(auth as ApiAuth, documentId),
      enabled: auth !== null,
    })),
  });
  const namedDocuments = documentQueries.flatMap((query) => {
    if (query.data === undefined || !query.data.ok) {
      return [];
    }
    return [
      {
        document_id: query.data.document.document_id,
        title: query.data.document.title,
      },
    ];
  });

  const analyzeMutation = useMutation({
    mutationFn: async (plan: TableQueryPlan) => {
      if (auth === null) {
        throw new Error("unsigned");
      }
      return analyzeTable(auth, plan);
    },
  });

  if (!session.ready || accessToken === null) {
    return (
      <div className={styles.page}>
        <PageHeader />
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const listError =
    tablesQuery.error !== null && tablesQuery.error !== undefined
      ? isClassifiedApiError(tablesQuery.error)
        ? apiFailureBanner(tablesQuery.error.failure)
        : GENERIC_PRODUCTION_ERROR
      : null;
  const analyzeError =
    analyzeMutation.error !== null && analyzeMutation.error !== undefined
      ? isClassifiedApiError(analyzeMutation.error)
        ? apiFailureBanner(analyzeMutation.error.failure)
        : GENERIC_PRODUCTION_ERROR
      : null;
  const tablesPending = tablesQuery.isPending && tablesQuery.data === undefined;
  const emptyCopy = tablesEmptyCopy(visibleManifests.length);
  const selectedDocumentName =
    selected === null
      ? ""
      : documentDisplayName(namedDocuments, selected.document_id);
  const seededDocumentName = scopedToDocument
    ? documentDisplayName(namedDocuments, documentIdParam)
    : "";

  /**
   * Compile the draft and POST only a valid extra-forbid plan.
   */
  function handleAnalyze(): void {
    if (selected === null) {
      return;
    }
    const compiled = compileTablePlanDraft(selected, draft);
    if (!compiled.ok) {
      setCompileError(tablePlanCompileCopy(compiled.reason));
      return;
    }
    setCompileError(null);
    setSubmittedPlan(compiled.plan);
    analyzeMutation.mutate(compiled.plan);
  }

  const tableOptions = [
    { value: "", label: "Select a table", disabled: true },
    ...visibleManifests.map((item) => ({
      value: item.table_id,
      label: item.sheet_name
        ? `${item.table_name} (${item.sheet_name})`
        : item.table_name,
    })),
  ];
  const listHeading = scopedToDocument
    ? "Tables in this document"
    : "Available tables";

  return (
    <div className={styles.page}>
      <PageHeader description="Run bounded calculations on structured data with exact cell provenance." />
      {listError ? (
        <StatusBanner kind="error" role="alert">
          {listError}
        </StatusBanner>
      ) : null}
      {compileError ? (
        <StatusBanner kind="warning" role="alert">
          {compileError}
        </StatusBanner>
      ) : null}
      {analyzeError ? (
        <StatusBanner kind="error" role="alert">
          {analyzeError}
        </StatusBanner>
      ) : null}
      {scopedToDocument ? (
        <TablesDocumentBar
          documentId={documentIdParam}
          documentName={seededDocumentName}
        />
      ) : null}

      <div className={styles.layout}>
        <aside className={styles.sidebar} aria-label={listHeading}>
          <h2>{listHeading}</h2>
          {tablesPending ? (
            <Skeleton label="Loading tables" width="100%" />
          ) : listError ? (
            <Button
              type="button"
              variant="secondary"
              data-action-id="tables.retry"
              onClick={() => {
                void tablesQuery.refetch();
              }}
            >
              Retry
            </Button>
          ) : visibleManifests.length === 0 ? (
            <p className={styles.muted}>{emptyCopy.title}</p>
          ) : (
            <ul className={styles.manifestList}>
              {visibleManifests.map((item) => {
                const active = selected?.table_id === item.table_id;
                return (
                  <li key={item.table_id} className={styles.manifestItem}>
                    <button
                      type="button"
                      className={
                        active ? styles.manifestButtonActive : styles.manifestButton
                      }
                      aria-current={active ? "true" : undefined}
                      onClick={() => setUserSelectedId(item.table_id)}
                    >
                      <UserText value={item.table_name} />
                      {item.sheet_name ? (
                        <>
                          {" "}
                          (<UserText value={item.sheet_name} />)
                        </>
                      ) : null}
                    </button>
                    {scopedToDocument ? null : (
                      <Link
                        href={`/documents/${encodeURIComponent(item.document_id)}`}
                        className={styles.documentLink}
                      >
                        <UserText
                          value={documentDisplayName(
                            namedDocuments,
                            item.document_id,
                          )}
                        />
                      </Link>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        <div className={styles.main}>
          <div className={styles.manifestPicker}>
            <Select
              label={listHeading}
              value={selected?.table_id ?? ""}
              options={tableOptions}
              onChange={(event) => setUserSelectedId(event.target.value)}
            />
            {tablesPending ? (
              <Skeleton label="Loading tables" width="100%" />
            ) : listError ? null : visibleManifests.length === 0 ? (
              <p className={styles.muted}>{emptyCopy.title}</p>
            ) : null}
          </div>
          {listError || tablesPending ? null : selected === null ? (
            <EmptyState
              title={emptyCopy.title}
              body={emptyCopy.body}
              action={
                <Button type="button" disabled>
                  Analyze
                </Button>
              }
            />
          ) : (
            <AnalysisPlan
              manifests={visibleManifests}
              selected={selected}
              documentName={selectedDocumentName}
              draft={draft}
              pending={analyzeMutation.isPending}
              onSelectTableId={setUserSelectedId}
              onDraftChange={(next) => {
                setDraft(next);
              }}
              onAnalyze={handleAnalyze}
            />
          )}
          {submittedPlan && analyzeMutation.isSuccess && analyzeMutation.data ? (
            <AnalysisResults
              result={analyzeMutation.data}
              selected={selected}
              documentName={documentDisplayName(
                namedDocuments,
                analyzeMutation.data.document_id,
              )}
              displaySortKey={displaySortKey}
              displaySortDir={displaySortDir}
              onDisplaySortKey={setDisplaySortKey}
              onDisplaySortDir={setDisplaySortDir}
            />
          ) : null}
        </div>
      </div>
    </div>
  );
}

/**
 * Empty-state copy for the global list or a document seed.
 *
 * @param visibleCount - Authorized manifests remaining after document scoping.
 * @returns Title and optional body. Analyze stays disabled in the caller.
 */
function tablesEmptyCopy(visibleCount: number): { title: string; body?: string } {
  if (visibleCount === 0) {
    return { title: EMPTY_MANIFESTS_COPY };
  }
  return {
    title: "Pick a table to analyze",
    body: "Deterministic calculations with exact cell provenance.",
  };
}
