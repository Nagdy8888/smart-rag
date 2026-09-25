/**
 * Evaluation workspace: task views, case list, regenerate, and exam results.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  fetchPdfEvalCase,
  listDocuments,
  listPdfEvalCases,
  regeneratePdfEvalDrafts,
  type ApiAuth,
} from "../../lib/api";
import { readEvalExamPointer } from "../../lib/eval-exam-pointer";
import {
  EVAL_LIST_MAX_ITEMS,
  EVAL_LIST_PAGE_SIZE,
  filterEvalCasesByGoldState,
  type EvalGoldStateFilter,
} from "../../lib/eval-workspace";
import { sessionQueryKeys } from "../../lib/query-keys";
import type { PdfEvalCaseSummary, PdfEvalStatus } from "../../lib/types";
import { ErrorState } from "../ui/error-state";
import { Spinner } from "../ui/spinner";
import { StatusBanner } from "../ui/status-banner";
import { EvaluationCaseEditor } from "./evaluation-case-editor";
import { EvaluationCaseList } from "./evaluation-case-list";
import { EvaluationExamBoard } from "./evaluation-exam-board";
import { EvaluationOverview } from "./evaluation-overview";
import { nextReviewCase, type EvaluationView } from "./evaluation-presenters";
import { EvaluationTaskTabs } from "./evaluation-task-tabs";
import styles from "./evaluation.module.css";

export type EvaluationWorkspaceProps = {
  /** Authenticated owner/admin caller. */
  auth: ApiAuth;
  /** Workspace status counts. */
  status: PdfEvalStatus | undefined;
};

type ExtraPageState = {
  revision: number;
  extra: PdfEvalCaseSummary[];
  cursor: string | null;
};

/**
 * Own task navigation, case-list queries, regeneration, and panel switching.
 *
 * @param props - Authenticated caller and status counts.
 * @returns Workspace body.
 */
export function EvaluationWorkspace({ auth, status }: EvaluationWorkspaceProps) {
  const queryClient = useQueryClient();
  const keys = sessionQueryKeys(auth.accessToken);
  const [view, setView] = useState<EvaluationView>(() =>
    readEvalExamPointer() ? "results" : "overview",
  );
  const [split, setSplit] = useState("all");
  const [review, setReview] = useState("all");
  const [goldState, setGoldState] = useState<EvalGoldStateFilter>("all");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [regenDocumentId, setRegenDocumentId] = useState("");
  const [regenNotice, setRegenNotice] = useState<string | null>(null);
  const [pages, setPages] = useState<ExtraPageState>({
    revision: 0,
    extra: [],
    cursor: null,
  });
  const casesQuery = useQuery({
    queryKey: keys.pdfEvalCaseList(split, review),
    queryFn: () =>
      listPdfEvalCases(auth, fetch, {
        split: split === "all" ? undefined : split,
        review_status: review === "all" ? undefined : review,
        limit: EVAL_LIST_PAGE_SIZE,
      }),
    retry: false,
  });
  const documentsQuery = useQuery({
    queryKey: ["pdf-eval-documents", auth.accessToken],
    queryFn: () => listDocuments(auth, { limit: 20 }),
    retry: false,
  });
  const listRevision = casesQuery.dataUpdatedAt;
  if (listRevision !== 0 && pages.revision !== listRevision) {
    setPages({
      revision: listRevision,
      extra: [],
      cursor: casesQuery.data?.next_case_id ?? null,
    });
  }
  const accumulated = useMemo(() => {
    const first = casesQuery.data?.items ?? [];
    const seen = new Set(first.map((item) => item.case_id));
    const extra = pages.extra.filter((item) => {
      if (seen.has(item.case_id)) {
        return false;
      }
      seen.add(item.case_id);
      return true;
    });
    return [...first, ...extra];
  }, [casesQuery.data?.items, pages.extra]);
  const items = filterEvalCasesByGoldState(accumulated, goldState);
  const selected = selectedId ?? items[0]?.case_id ?? null;
  const detailQuery = useQuery({
    queryKey: keys.pdfEvalCase(selected),
    queryFn: () => fetchPdfEvalCase(auth, selected as string),
    enabled: view === "cases" && selected !== null,
    retry: false,
  });
  const preferredDocument =
    documentsQuery.data?.[0]?.document_id ?? status?.document_id ?? "";
  const activeRegenDocumentId =
    regenDocumentId === "" ? preferredDocument : regenDocumentId;
  const nextCaseId =
    accumulated.length >= EVAL_LIST_MAX_ITEMS
      ? null
      : pages.extra.length > 0
        ? pages.cursor
        : (casesQuery.data?.next_case_id ?? null);
  const loadMore = useMutation({
    mutationFn: async () => {
      if (nextCaseId === null) {
        throw new Error("request_rejected");
      }
      return listPdfEvalCases(auth, fetch, {
        split: split === "all" ? undefined : split,
        review_status: review === "all" ? undefined : review,
        after: nextCaseId,
        limit: EVAL_LIST_PAGE_SIZE,
      });
    },
    onSuccess: (page) => {
      setPages((current) => ({
        ...current,
        extra: [...current.extra, ...page.items].slice(0, EVAL_LIST_MAX_ITEMS),
        cursor: page.next_case_id,
      }));
    },
  });
  const regenerate = useMutation({
    mutationFn: () => regeneratePdfEvalDrafts(auth, activeRegenDocumentId),
    onSuccess: async (result) => {
      setRegenNotice(
        `Created ${String(result.inserted_count ?? 0)} draft cases. Review them before running an exam.`,
      );
      await queryClient.invalidateQueries({ queryKey: keys.pdfEvalCases });
      await queryClient.invalidateQueries({ queryKey: keys.pdfEvalStatus });
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message === "capacity_exceeded") {
        setRegenNotice(
          "The workspace is at capacity. Delete cases before regenerating.",
        );
        return;
      }
      if (error instanceof Error && error.message === "stale_row_version") {
        setRegenNotice("The workspace changed. Reloaded the latest cases.");
        void queryClient.invalidateQueries({ queryKey: keys.pdfEvalCases });
        return;
      }
      setRegenNotice("Drafts could not be regenerated.");
    },
  });

  if (casesQuery.error instanceof Error && casesQuery.error.message === "forbidden") {
    return (
      <ErrorState
        title="You don’t have access."
        message="Only owners and admins can open this page."
      />
    );
  }

  const listError = Boolean(casesQuery.error);
  const staleGoldCount = status?.stale_gold_count;
  const documentOptions = (documentsQuery.data ?? []).map((item) => ({
    value: item.document_id,
    label: item.title && item.title !== "" ? item.title : "Untitled document",
  }));
  const workspaceEmpty = (status?.case_count ?? accumulated.length) === 0;

  return (
    <div className={styles.stack}>
      {typeof staleGoldCount === "number" && staleGoldCount > 0 ? (
        <StatusBanner kind="warning" role="status">
          {`${String(staleGoldCount)} cases have stale sources. Remap those locators before approval or exam.`}
        </StatusBanner>
      ) : null}
      <EvaluationTaskTabs value={view} onChange={setView} />
      {view === "overview" ? (
        <EvaluationOverview
          status={status}
          documentOptions={documentOptions}
          regenDocumentId={activeRegenDocumentId}
          onRegenDocumentChange={setRegenDocumentId}
          regeneratePending={regenerate.isPending}
          onRegenerate={() => {
            setRegenNotice(null);
            regenerate.mutate();
          }}
          regenNotice={regenNotice}
          onReviewStale={() => {
            setGoldState("stale");
            setSelectedId(accumulated.find((item) => item.gold_stale)?.case_id ?? null);
            setView("cases");
          }}
          onReviewNext={() => {
            const next = nextReviewCase(accumulated);
            setSelectedId(next?.case_id ?? null);
            setView("cases");
          }}
          onViewResults={() => setView("results")}
        />
      ) : null}
      {view === "cases" ? (
        <div
          role="tabpanel"
          id="eval-panel-cases"
          aria-labelledby="eval-tab-cases"
          className={styles.layout}
        >
          {listError ? (
            <ErrorState
              title="Cases could not load."
              message="Try again. Holdout files are never listed here."
            />
          ) : null}
          {!listError && casesQuery.isPending ? <Spinner label="Loading cases" /> : null}
          {!listError && !casesQuery.isPending ? (
            <EvaluationCaseList
              split={split}
              review={review}
              goldState={goldState}
              onSplit={(value) => {
                setSplit(value);
                setSelectedId(null);
              }}
              onReview={(value) => {
                setReview(value);
                setSelectedId(null);
              }}
              onGoldState={(value) => {
                setGoldState(value);
                setSelectedId(null);
              }}
              onClearFilters={() => {
                setSplit("all");
                setReview("all");
                setGoldState("all");
                setSelectedId(null);
              }}
              items={items}
              selected={selected}
              onSelect={setSelectedId}
              nextCaseId={nextCaseId}
              loadMorePending={loadMore.isPending}
              onLoadMore={() => loadMore.mutate()}
              workspaceEmpty={workspaceEmpty}
              onGoOverview={() => setView("overview")}
            />
          ) : null}
          <div>
            {detailQuery.isPending ? <Spinner label="Loading case" /> : null}
            {detailQuery.data ? (
              <EvaluationCaseEditor
                key={`${detailQuery.data.case_id}:${String(detailQuery.data.row_version)}`}
                auth={auth}
                detail={detailQuery.data}
                onSaved={() => {
                  void queryClient.invalidateQueries({ queryKey: keys.pdfEvalCases });
                  void queryClient.invalidateQueries({ queryKey: keys.pdfEvalStatus });
                  void queryClient.invalidateQueries({
                    queryKey: keys.pdfEvalCase(selected),
                  });
                }}
                onSelectNext={() => {
                  const index = items.findIndex((item) => item.case_id === selected);
                  const next = items[index + 1] ?? items[0];
                  if (next) {
                    setSelectedId(next.case_id);
                  }
                }}
                onDeleted={() => {
                  const index = items.findIndex((item) => item.case_id === selected);
                  const next = items[index + 1] ?? items[index - 1] ?? null;
                  setSelectedId(next?.case_id ?? null);
                  void queryClient.invalidateQueries({ queryKey: keys.pdfEvalCases });
                  void queryClient.invalidateQueries({ queryKey: keys.pdfEvalStatus });
                }}
              />
            ) : null}
          </div>
        </div>
      ) : null}
      {view === "results" ? (
        <div
          role="tabpanel"
          id="eval-panel-results"
          aria-labelledby="eval-tab-results"
          className={styles.taskPanel}
        >
          <EvaluationExamBoard
            auth={auth}
            approvedCount={status?.approved_count ?? 0}
            onOpenCase={(caseId) => {
              setSelectedId(caseId);
              setView("cases");
            }}
          />
        </div>
      ) : null}
    </div>
  );
}
