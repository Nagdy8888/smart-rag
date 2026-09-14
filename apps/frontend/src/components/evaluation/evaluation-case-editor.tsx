/**
 * Case editor: details, required sources, approval, and a manual AI test.
 */

"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useRef, useState } from "react";
import {
  deletePdfEvalCase,
  fetchDocument,
  listPdfEvalPassages,
  patchPdfEvalCase,
  replacePdfEvalGold,
  setPdfEvalApproval,
  type ApiAuth,
} from "../../lib/api";
import {
  EVAL_LIST_PAGE_SIZE,
  evalCaseListLabel,
  toggleQuizGoldChunk,
} from "../../lib/eval-workspace";
import { sessionQueryKeys } from "../../lib/query-keys";
import type { PdfEvalCaseDetail, PdfEvalPassage } from "../../lib/types";
import { PDF_EVAL_QUERY_CLASSES } from "../../lib/types";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { ConfirmDialog } from "../ui/confirm-dialog";
import { Select } from "../ui/select";
import { StatusBanner } from "../ui/status-banner";
import { StatusPill } from "../ui/status-pill";
import { Textarea } from "../ui/textarea";
import { UserText } from "../ui/user-text";
import { EvaluationAiTestPanel } from "./evaluation-ai-test-panel";
import { EvaluationGoldPicker } from "./evaluation-gold-picker";
import {
  datasetLabel,
  evalApproveUiReason,
  evalDetailsDirty,
  parseEvalLines,
  queryClassLabel,
  reviewStatusLabel,
  reviewStatusTone,
  sourceStatusLabel,
  sourceStatusTone,
} from "./evaluation-presenters";
import styles from "./evaluation.module.css";

export type EvaluationCaseEditorProps = {
  /** Owner/admin bearer auth. */
  auth: ApiAuth;
  /** Authorized case detail. */
  detail: PdfEvalCaseDetail;
  /** Reload after a successful write. */
  onSaved: () => void;
  /** Select the next queue row. */
  onSelectNext: () => void;
  /** Select a neighbor after delete. */
  onDeleted: () => void;
};

type PassagePageState = {
  revision: number;
  extra: PdfEvalPassage[];
  cursor: string | null;
};

/**
 * Edit labels, remap required sources, approve, reject, delete, and test.
 *
 * @param props - Case detail and callbacks.
 * @returns Editor form.
 */
export function EvaluationCaseEditor({
  auth,
  detail,
  onSaved,
  onSelectNext,
  onDeleted,
}: EvaluationCaseEditorProps) {
  const keys = sessionQueryKeys(auth.accessToken);
  const [question, setQuestion] = useState(detail.question);
  const [expectedAnswer, setExpectedAnswer] = useState(detail.expected_answer);
  const [atomicFacts, setAtomicFacts] = useState(detail.atomic_facts.join("\n"));
  const [requiredTerms, setRequiredTerms] = useState(
    detail.required_terms.join("\n"),
  );
  const [queryClass, setQueryClass] = useState(detail.query_class);
  const [selectedChunkIds, setSelectedChunkIds] = useState(detail.chunk_ids);
  const [stale, setStale] = useState(false);
  const [revealAnswer, setRevealAnswer] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [goldError, setGoldError] = useState<string | null>(null);
  const [passagePages, setPassagePages] = useState<PassagePageState>({
    revision: 0,
    extra: [],
    cursor: null,
  });
  const deleteTrigger = useRef<HTMLButtonElement>(null);
  const documentId = detail.document_id ?? detail.gold[0]?.document_id ?? null;
  const passagesQuery = useQuery({
    queryKey: keys.pdfEvalPassages(documentId),
    queryFn: () =>
      listPdfEvalPassages(auth, {
        documentId: documentId as string,
        limit: EVAL_LIST_PAGE_SIZE,
      }),
    enabled: documentId !== null,
    retry: false,
  });
  const documentQuery = useQuery({
    queryKey: ["pdf-eval-document-title", documentId],
    queryFn: () => fetchDocument(auth, documentId as string),
    enabled: documentId !== null,
    retry: false,
  });
  const passageRevision = passagesQuery.dataUpdatedAt;
  if (passageRevision !== 0 && passagePages.revision !== passageRevision) {
    setPassagePages({
      revision: passageRevision,
      extra: [],
      cursor: passagesQuery.data?.next_chunk_id ?? null,
    });
  }
  const passages = useMemo(() => {
    const first = passagesQuery.data?.items ?? [];
    const seen = new Set(first.map((item) => item.chunk_id));
    const extra = passagePages.extra.filter((item) => {
      if (seen.has(item.chunk_id)) {
        return false;
      }
      seen.add(item.chunk_id);
      return true;
    });
    return [...first, ...extra];
  }, [passagesQuery.data?.items, passagePages.extra]);
  const nextChunkId =
    passagePages.extra.length > 0
      ? passagePages.cursor
      : (passagesQuery.data?.next_chunk_id ?? null);
  const detailsDirty = evalDetailsDirty({
    question,
    expectedAnswer,
    atomicFacts,
    requiredTerms,
    queryClass,
    detail,
  });
  const goldDirty = selectedChunkIds.join("\0") !== detail.chunk_ids.join("\0");
  const approveReason = evalApproveUiReason({
    detailsDirty,
    goldDirty,
    goldStale: detail.gold_stale,
    goldCount: detail.chunk_ids.length,
  });
  const approved = detail.review_status === "approved" || detail.human_approved;
  const reloadStale = () => {
    setStale(true);
    onSaved();
  };
  const save = useMutation({
    mutationFn: () =>
      patchPdfEvalCase(auth, detail.case_id, detail.row_version, {
        question,
        expected_answer: expectedAnswer,
        atomic_facts: parseEvalLines(atomicFacts),
        query_class: queryClass,
        required_terms: parseEvalLines(requiredTerms),
      }),
    onSuccess: () => {
      setStale(false);
      onSaved();
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message === "stale_row_version") {
        reloadStale();
      }
    },
  });
  const goldSave = useMutation({
    mutationFn: () =>
      replacePdfEvalGold(
        auth,
        detail.case_id,
        detail.row_version,
        selectedChunkIds,
      ),
    onSuccess: () => {
      setGoldError(null);
      setStale(false);
      onSaved();
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message === "stale_row_version") {
        reloadStale();
        return;
      }
      setGoldError("Gold could not be saved. Try again.");
    },
  });
  const approval = useMutation({
    mutationFn: (nextApproved: boolean) =>
      setPdfEvalApproval(auth, detail.case_id, detail.row_version, nextApproved),
    onSuccess: () => {
      onSaved();
      onSelectNext();
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message === "stale_row_version") {
        reloadStale();
      }
    },
  });
  const remove = useMutation({
    mutationFn: () => deletePdfEvalCase(auth, detail.case_id, detail.row_version),
    onSuccess: () => {
      setDeleteOpen(false);
      onDeleted();
    },
    onError: (error: unknown) => {
      setDeleteOpen(false);
      if (error instanceof Error && error.message === "stale_row_version") {
        reloadStale();
      }
    },
  });
  const loadMorePassages = useMutation({
    mutationFn: async () => {
      if (documentId === null || nextChunkId === null) {
        throw new Error("request_rejected");
      }
      return listPdfEvalPassages(auth, {
        documentId,
        after: nextChunkId,
        limit: EVAL_LIST_PAGE_SIZE,
      });
    },
    onSuccess: (page) => {
      setPassagePages((current) => ({
        ...current,
        extra: [...current.extra, ...page.items],
        cursor: page.next_chunk_id,
      }));
    },
  });
  const documentTitle =
    documentQuery.data && documentQuery.data.ok
      ? (documentQuery.data.document.title ?? "Untitled document")
      : "Current document";
  const namedCase = evalCaseListLabel({
    query_class: detail.query_class,
    split: detail.split,
    review_status: detail.review_status,
    human_approved: detail.human_approved,
  });
  const queryClassOptions = PDF_EVAL_QUERY_CLASSES.map((value) => ({
    value,
    label: queryClassLabel(value),
  }));
  const reviewLabel = reviewStatusLabel(detail.review_status, detail.human_approved);

  return (
    <div className={styles.editor}>
      <header className={styles.editorHeader}>
        <h3>
          <UserText value={queryClassLabel(detail.query_class)} />
        </h3>
        <span className={styles.caseMeta}>
          <Badge label={datasetLabel(detail.split)} />
          <StatusPill
            status={reviewLabel}
            tone={reviewStatusTone(detail.review_status, detail.human_approved)}
          />
          <StatusPill
            status={sourceStatusLabel(detail.gold_stale)}
            tone={sourceStatusTone(detail.gold_stale)}
          />
        </span>
      </header>
      {stale ? (
        <StatusBanner kind="info" role="status">
          This case changed. Reloaded the latest version.
        </StatusBanner>
      ) : null}
      {detail.gold_stale ? (
        <StatusBanner kind="warning" role="status">
          This document version changed. Remap required sources from current
          passages and reapprove.
        </StatusBanner>
      ) : null}
      {approved && (detailsDirty || goldDirty) ? (
        <StatusBanner kind="warning" role="status">
          Saving changes will return this case to draft review.
        </StatusBanner>
      ) : null}
      {detailsDirty ? (
        <p className={styles.muted} role="status">
          Unsaved case details
        </p>
      ) : null}
      {goldDirty ? (
        <p className={styles.muted} role="status">
          Unsaved source changes
        </p>
      ) : null}
      <section className={styles.section}>
        <h3>Question and expected answer</h3>
        <Textarea
          label="Question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          fullWidth
        />
        <Textarea
          label="Expected answer"
          value={expectedAnswer}
          onChange={(event) => setExpectedAnswer(event.target.value)}
          fullWidth
        />
        <Select
          label="Question type"
          value={queryClass}
          options={
            queryClassOptions.some((item) => item.value === queryClass)
              ? queryClassOptions
              : [{ value: queryClass, label: queryClassLabel(queryClass) }, ...queryClassOptions]
          }
          onChange={(event) => setQueryClass(event.target.value)}
        />
      </section>
      <section className={styles.section}>
        <h3>Scoring guidance</h3>
        <p className={styles.muted}>Enter one item per line.</p>
        <Textarea
          label="Atomic facts"
          value={atomicFacts}
          onChange={(event) => setAtomicFacts(event.target.value)}
          fullWidth
        />
        <Textarea
          label="Required terms"
          value={requiredTerms}
          onChange={(event) => setRequiredTerms(event.target.value)}
          fullWidth
        />
      </section>
      <EvaluationGoldPicker
        documentTitle={documentTitle}
        passages={passages}
        selectedIds={selectedChunkIds}
        gold={detail.gold}
        onToggle={(chunkId) => {
          const next = toggleQuizGoldChunk(selectedChunkIds, chunkId);
          setSelectedChunkIds(next.next);
        }}
        nextChunkId={nextChunkId}
        loadMorePending={loadMorePassages.isPending}
        onLoadMore={() => loadMorePassages.mutate()}
        savePending={goldSave.isPending}
        onSave={() => goldSave.mutate()}
        saveError={goldError}
        selectionDirty={goldDirty}
      />
      <div className={styles.editorFooter}>
        <Button
          type="button"
          data-action-id="eval.save"
          variant={detailsDirty ? "primary" : "secondary"}
          pending={save.isPending}
          pendingLabel="Saving…"
          disabled={!detailsDirty}
          disabledReason={detailsDirty ? undefined : "No case detail changes to save."}
          onClick={() => save.mutate()}
        >
          Save details
        </Button>
        <Button
          type="button"
          data-action-id="eval.approve"
          variant={approveReason === null ? "primary" : "secondary"}
          pending={approval.isPending}
          pendingLabel="Approving…"
          disabled={approveReason !== null}
          disabledReason={approveReason ?? undefined}
          onClick={() => approval.mutate(true)}
        >
          Approve case
        </Button>
        <Button
          type="button"
          variant="dangerQuiet"
          data-action-id="eval.reject"
          onClick={() => approval.mutate(false)}
        >
          Reject
        </Button>
        <Button
          type="button"
          variant="ghost"
          data-action-id="eval.next"
          onClick={onSelectNext}
        >
          Next case
        </Button>
        <Button
          ref={deleteTrigger}
          type="button"
          variant="dangerQuiet"
          data-action-id="eval.delete"
          onClick={() => setDeleteOpen(true)}
        >
          Delete
        </Button>
      </div>
      {deleteOpen ? (
        <ConfirmDialog
          title="Delete this quiz case?"
          confirmLabel="Delete case"
          pendingLabel="Deleting…"
          danger
          pending={remove.isPending}
          returnFocusRef={deleteTrigger}
          onClose={() => setDeleteOpen(false)}
          onConfirm={() => remove.mutate()}
        >
          This immediately deletes{" "}
          <UserText value={namedCase} />. It cannot be undone.
        </ConfirmDialog>
      ) : null}
      <EvaluationAiTestPanel
        auth={auth}
        caseId={detail.case_id}
        split={detail.split}
        question={question}
        expectedAnswer={expectedAnswer}
        revealAnswer={revealAnswer}
        onReveal={() => setRevealAnswer(true)}
      />
    </div>
  );
}
