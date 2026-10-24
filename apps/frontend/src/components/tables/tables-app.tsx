/**
 * Structured tables: authorized manifests, guided TableQueryPlan, deterministic rows.
 * No SQL textarea. No client-summed totals. No Export, Save, or Share.
 */

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AnalysisPlan } from "./analysis-plan";
import { AnalysisResults } from "./analysis-results";
import { TablesDocumentBar } from "./tables-document-bar";
import { Button } from "../ui/button";
import { EmptyState } from "../ui/empty-state";
import { PageHeader } from "../ui/page-header";
import { Input } from "../ui/input";
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
  buildTableQueryPlan,
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
  const documentScope = documentIdParam ?? "";
  const [userSelectedId, setUserSelectedId] = useState<string | null>(null);
  const [selectionScope, setSelectionScope] = useState(documentScope);
  const scopedUserSelectedId =
    selectionScope === documentScope ? userSelectedId : null;
  const [draft, setDraft] = useState<TablePlanDraft>(EMPTY_TABLE_PLAN_DRAFT);
  const [tableSearch, setTableSearch] = useState("");
  const [compileError, setCompileError] = useState<string | null>(null);
  const [submittedPlan, setSubmittedPlan] = useState<TableQueryPlan | null>(null);
  const [displaySortKey, setDisplaySortKey] = useState<string | null>(null);
  const [displaySortDir, setDisplaySortDir] = useState<"asc" | "desc">("asc");

  /**
   * Remember a table pick for the current document query string.
   *
   * @param tableId - Manifest table id.
   */
  const selectTableId = (tableId: string): void => {
    setSelectionScope(documentScope);
    setUserSelectedId(tableId);
    setDraft(EMPTY_TABLE_PLAN_DRAFT);
    setCompileError(null);
    setSubmittedPlan(null);
    setDisplaySortKey(null);
    setDisplaySortDir("asc");
    analyzeMutation.reset();
  };

  const tablesQuery = useQuery({
    queryKey: keys.tables,
    queryFn: () => listTables(auth as ApiAuth),
    enabled: auth !== null,
  });

  const manifests = tablesQuery.data ?? [];
  const visibleManifests = manifestsForDocument(manifests, documentIdParam);
  const selected = resolveSelectedManifest(
    visibleManifests,
    scopedUserSelectedId,
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

  const matchingManifests = visibleManifests.filter((item) => [item.table_name, item.sheet_name, documentDisplayName(namedDocuments, item.document_id)].some((value) => value?.toLowerCase().includes(tableSearch.trim().toLowerCase())));

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
        ? analyzeMutation.error.failure.kind === "deleted"
          ? "This table is unavailable or access has changed. Reload the table list and select it again."
          : apiFailureBanner(analyzeMutation.error.failure)
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
      label: `${item.sheet_name || item.table_name.replace(/_/g, " ")} / ${documentDisplayName(namedDocuments, item.document_id)}`,
    })),
  ];
  const listHeading = scopedToDocument
    ? "Tables in this document"
    : "Available tables";

  return (
    <div className={styles.page}>
      <PageHeader description="Filter, group, and compare values from tables in your documents." />
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
          {analyzeError} <Button type="button" variant="secondary" onClick={() => { analyzeMutation.reset(); void tablesQuery.refetch(); }}>Reload tables</Button>
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
          <Input label="Find a table" type="search" fullWidth placeholder="Table, sheet, or document" value={tableSearch} onChange={(event) => setTableSearch(event.target.value)} />
          {!tablesPending && !listError ? <p className={styles.muted} role="status">{matchingManifests.length} of {visibleManifests.length} tables</p> : null}
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
            <>
            {matchingManifests.length === 0 ? <div className={styles.section}><p className={styles.muted}>No tables match your search.</p><Button type="button" variant="secondary" onClick={() => setTableSearch("")}>Clear table search</Button></div> : null}
            <ul className={styles.manifestList}>
              {matchingManifests.map((item) => {
                const active = selected?.table_id === item.table_id;
                return (
                  <li key={item.table_id} className={styles.manifestItem}>
                    <button
                      type="button"
                      className={
                        active ? styles.manifestButtonActive : styles.manifestButton
                      }
                      title={item.table_name}
                      aria-current={active ? "true" : undefined}
                      onClick={() => selectTableId(item.table_id)}
                    >
                      <UserText value={item.sheet_name || item.table_name.replace(/_/g, " ")} />
                      <span className={styles.manifestMeta}>{item.row_count === null ? "Row count unavailable" : `${item.row_count.toLocaleString()} rows`}{item.column_count === null ? "" : ` / ${item.column_count} columns`}</span>
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
            </>
          )}
        </aside>

        <div className={styles.main}>
          <div className={styles.manifestPicker}>
            <Select
              label={listHeading}
              value={selected?.table_id ?? ""}
              options={tableOptions}
              onChange={(event) => selectTableId(event.target.value)}
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
              key={selected.table_id}
              selected={selected}
              documentName={selectedDocumentName}
              draft={draft}
              pending={analyzeMutation.isPending}
              onDraftChange={(next) => {
                setDraft(next);
              }}
              onReset={() => { setDraft(EMPTY_TABLE_PLAN_DRAFT); setCompileError(null); }}
              onCountRows={() => {
                if (analyzeMutation.isPending) return;
                const plan = buildTableQueryPlan({ table_id: selected.table_id, version_id: selected.version_id, aggregations: [{ op: "count", alias: "row_count" }] });
                setCompileError(null);
                setSubmittedPlan(plan);
                setDisplaySortKey(null);
                analyzeMutation.mutate(plan);
              }}
              onAnalyze={handleAnalyze}
            />
          )}
          {submittedPlan && analyzeMutation.isSuccess && analyzeMutation.data && analyzeMutation.data.table_id === selected?.table_id && analyzeMutation.data.version_id === selected.version_id ? (
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
    body: "Pick a table to analyze. Every result links back to the cells it came from.",
  };
}
