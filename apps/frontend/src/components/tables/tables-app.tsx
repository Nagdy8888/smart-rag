/**
 * Structured tables: authorized manifests, guided TableQueryPlan, deterministic rows.
 * No SQL textarea. No client-summed totals. No Export, Save, or Share.
 */

"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AnalysisPlan } from "./analysis-plan";
import { AnalysisResults } from "./analysis-results";
import { EmptyState } from "../ui/empty-state";
import { PageHeader } from "../ui/page-header";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
import {
  analyzeTable,
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
  resolveSelectedManifest,
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
  const [userSelectedId, setUserSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState<TablePlanDraft>(EMPTY_TABLE_PLAN_DRAFT);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [submittedPlan, setSubmittedPlan] = useState<TableQueryPlan | null>(null);
  const [displaySortKey, setDisplaySortKey] = useState<string | null>(null);
  const [displaySortDir, setDisplaySortDir] = useState<"asc" | "desc">("asc");

  const tablesQuery = useQuery({
    queryKey: keys.tables,
    queryFn: () => listTables(auth as ApiAuth),
    enabled: auth !== null,
  });

  const manifests = tablesQuery.data ?? [];
  const selected = resolveSelectedManifest(
    manifests,
    userSelectedId,
    tableIdParam,
    documentIdParam,
  );

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
        <PageHeader title="Tables." />
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
    ...manifests.map((item) => ({
      value: item.table_id,
      label: item.sheet_name
        ? `${item.table_name} (${item.sheet_name})`
        : item.table_name,
    })),
  ];

  return (
    <div className={styles.page}>
      <PageHeader
        title="Tables."
        description="Run bounded calculations on structured data with exact cell provenance."
      />
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

      <div className={styles.layout}>
        <aside className={styles.sidebar} aria-label="Available tables">
          <h2>Available tables.</h2>
          {manifests.length === 0 ? (
            <EmptyState title={EMPTY_MANIFESTS_COPY} />
          ) : (
            <ul className={styles.manifestList}>
              {manifests.map((item) => {
                const active = selected?.table_id === item.table_id;
                return (
                  <li key={item.table_id}>
                    <button
                      type="button"
                      className={
                        active ? styles.manifestButtonActive : styles.manifestButton
                      }
                      aria-current={active ? "true" : undefined}
                      onClick={() => setUserSelectedId(item.table_id)}
                    >
                      <span>
                        <UserText value={item.table_name} />
                        {item.sheet_name ? (
                          <>
                            {" "}
                            (<UserText value={item.sheet_name} />)
                          </>
                        ) : null}
                      </span>
                      <span className={styles.mono}>
                        <UserText value={item.document_id} />
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </aside>

        <div className={styles.main}>
          <div className={styles.manifestPicker}>
            <Select
              label="Available tables"
              value={selected?.table_id ?? ""}
              options={tableOptions}
              onChange={(event) => setUserSelectedId(event.target.value)}
            />
            {manifests.length === 0 ? (
              <EmptyState title={EMPTY_MANIFESTS_COPY} />
            ) : null}
          </div>
          <AnalysisPlan
            manifests={manifests}
            selected={selected}
            draft={draft}
            pending={analyzeMutation.isPending}
            onSelectTableId={setUserSelectedId}
            onDraftChange={(next) => {
              setDraft(next);
            }}
            onAnalyze={handleAnalyze}
          />
          {submittedPlan ? (
            <section className={styles.card} aria-label="Submitted plan">
              <h2>Submitted plan</h2>
              <pre className={styles.planPre}>
                <UserText value={JSON.stringify(submittedPlan, null, 2)} />
              </pre>
            </section>
          ) : null}
          {submittedPlan && analyzeMutation.isSuccess && analyzeMutation.data ? (
            <AnalysisResults
              result={analyzeMutation.data}
              selected={selected}
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
