/**
 * Admin Evaluation workspace: review, approve, source preview, and AI test.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState, type RefObject } from "react";
import {
  comparePdfEvalRun,
  fetchPdfEvalCase,
  fetchPdfEvalStatus,
  listPdfEvalCases,
  listPdfEvalPassages,
  patchPdfEvalCase,
  setPdfEvalApproval,
  type ApiAuth,
} from "../../lib/api";
import { useSession } from "../../lib/auth/session-provider";
import {
  citationCompareAllowed,
  evalAiRequestBody,
  holdoutCannotRun,
} from "../../lib/eval-workspace";
import { evaluatePaidHandshake } from "../../lib/handshake";
import { sessionQueryKeys } from "../../lib/query-keys";
import { Button, PrimaryAction } from "../ui/button";
import { ErrorState } from "../ui/error-state";
import { Sheet } from "../ui/sheet";
import { Spinner } from "../ui/spinner";
import { Textarea } from "../ui/textarea";
import { UserText } from "../ui/user-text";
import { useChatQueries } from "../chat/hooks/use-chat-queries";
import { useChatRun } from "../chat/hooks/use-chat-run";
import shellStyles from "../admin/admin-shell.module.css";
import tableStyles from "../admin/admin-tables.module.css";
import styles from "./evaluation.module.css";

const combined = { ...shellStyles, ...tableStyles, ...styles };

/**
 * Render the local PDF evaluation workspace.
 *
 * Capability is gated by `/api/meta`. Private content still requires a real
 * owner/admin GET. Hidden nav is not authorization.
 *
 * @returns Evaluation panel, or a permission/error state.
 */
export function EvaluationPanel() {
  const session = useSession();
  const accessToken = session.accessToken;
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);
  const statusQuery = useQuery({
    queryKey: keys.pdfEvalStatus,
    queryFn: () => fetchPdfEvalStatus(auth as ApiAuth),
    enabled: auth !== null,
    retry: false,
  });

  if (!session.ready || accessToken === null || auth === null) {
    return <p className={combined.muted}>Sign in to review evaluation cases.</p>;
  }
  if (statusQuery.isPending) {
    return <Spinner label="Loading evaluation workspace" />;
  }
  if (statusQuery.error instanceof Error && statusQuery.error.message === "forbidden") {
    return (
      <ErrorState
        title="You don’t have access."
        message="This area is limited to owners and admins. The server denied the request."
      />
    );
  }
  if (statusQuery.error) {
    return (
      <ErrorState
        title="Evaluation is unavailable."
        message="The evaluation workspace could not be loaded."
      />
    );
  }

  return (
    <section className={combined.panel} aria-label="Evaluation workspace">
      <h2>Evaluation</h2>
      <p className={combined.muted}>
        Review source-bound questions, approve labels, and run a manual AI test
        through production Ask. Official Recall@10 stays on the CLI.
      </p>
      <EvaluationWorkspace auth={auth} />
    </section>
  );
}

type WorkspaceProps = {
  auth: ApiAuth;
};

/**
 * Case list, editor, passages, and AI test.
 *
 * @param props - Authenticated caller.
 * @returns Workspace body.
 */
function EvaluationWorkspace({ auth }: WorkspaceProps) {
  const queryClient = useQueryClient();
  const keys = sessionQueryKeys(auth.accessToken);
  const casesQuery = useQuery({
    queryKey: keys.pdfEvalCases,
    queryFn: () => listPdfEvalCases(auth),
    retry: false,
  });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [passagesOpen, setPassagesOpen] = useState(false);
  const passagesTrigger = useRef<HTMLButtonElement>(null);
  const selected = selectedId ?? casesQuery.data?.items[0]?.case_id ?? null;
  const detailQuery = useQuery({
    queryKey: keys.pdfEvalCase(selected),
    queryFn: () => fetchPdfEvalCase(auth, selected as string),
    enabled: selected !== null,
    retry: false,
  });
  const passagesQuery = useQuery({
    queryKey: keys.pdfEvalPassages,
    queryFn: () => listPdfEvalPassages(auth),
    enabled: passagesOpen,
    retry: false,
  });

  if (casesQuery.isPending) {
    return <Spinner label="Loading cases" />;
  }
  if (casesQuery.error) {
    return (
      <ErrorState
        title="Cases could not load."
        message="Try again. Holdout files are never listed here."
      />
    );
  }
  const items = casesQuery.data?.items ?? [];
  return (
    <div className={combined.layout}>
      <nav aria-label="Evaluation cases">
        <ul className={combined.caseList}>
          {items.map((item) => {
            const current = item.case_id === selected;
            return (
              <li key={item.case_id}>
                <button
                  type="button"
                  className={
                    current ? combined.caseButtonCurrent : combined.caseButton
                  }
                  aria-current={current ? "true" : undefined}
                  onClick={() => setSelectedId(item.case_id)}
                >
                  <UserText value={item.query_class} />
                  <span className={combined.muted}>
                    {" "}
                    {item.human_approved ? "approved" : "draft"} · {item.split}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>
      <div>
        {detailQuery.isPending ? <Spinner label="Loading case" /> : null}
        {detailQuery.data ? (
          <CaseEditor
            key={`${detailQuery.data.case_id}:${detailQuery.data.revision}`}
            auth={auth}
            detail={detailQuery.data}
            onSaved={() => {
              void queryClient.invalidateQueries({ queryKey: keys.pdfEvalCases });
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
            onOpenPassages={() => setPassagesOpen(true)}
            passagesTrigger={passagesTrigger}
          />
        ) : null}
      </div>
      {passagesOpen ? (
        <Sheet
          title="Source passages"
          onClose={() => setPassagesOpen(false)}
          returnFocusRef={passagesTrigger}
        >
          {passagesQuery.isPending ? <Spinner label="Loading passages" /> : null}
          {(passagesQuery.data ?? []).map((item) => (
            <p key={item.chunk_id} className={combined.preview} dir="auto">
              <UserText value={item.raw_text} />
            </p>
          ))}
        </Sheet>
      ) : null}
    </div>
  );
}

type CaseEditorProps = {
  auth: ApiAuth;
  detail: Awaited<ReturnType<typeof fetchPdfEvalCase>>;
  onSaved: () => void;
  onSelectNext: () => void;
  onOpenPassages: () => void;
  passagesTrigger: RefObject<HTMLButtonElement | null>;
};

/**
 * Edit, approve, and run a manual AI test for one case.
 *
 * @param props - Case detail and callbacks.
 * @returns Editor form.
 */
function CaseEditor({
  auth,
  detail,
  onSaved,
  onSelectNext,
  onOpenPassages,
  passagesTrigger,
}: CaseEditorProps) {
  const [question, setQuestion] = useState(detail.question);
  const answer = detail.expected_answer;
  const [stale, setStale] = useState(false);
  const [revealAnswer, setRevealAnswer] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      patchPdfEvalCase(auth, detail.case_id, detail.revision, {
        question,
        expected_answer: answer,
      }),
    onSuccess: () => {
      setStale(false);
      onSaved();
    },
    onError: (error: unknown) => {
      if (error instanceof Error && error.message === "stale_workspace_revision") {
        setStale(true);
        onSaved();
      }
    },
  });
  const approval = useMutation({
    mutationFn: (approved: boolean) =>
      setPdfEvalApproval(auth, detail.case_id, detail.revision, approved),
    onSuccess: () => {
      onSaved();
      onSelectNext();
    },
  });

  return (
    <div className={combined.formGrid}>
      {stale ? (
        <p className={combined.muted} role="status">
          This case changed. Reloaded the latest revision.
        </p>
      ) : null}
      <Textarea
        label="Question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        fullWidth
      />
      <div className={combined.actions}>
        <Button
          type="button"
          data-action-id="eval.save"
          pending={save.isPending}
          pendingLabel="Saving…"
          onClick={() => save.mutate()}
        >
          Save
        </Button>
        <Button
          type="button"
          data-action-id="eval.approve"
          pending={approval.isPending}
          pendingLabel="Approving…"
          onClick={() => approval.mutate(true)}
        >
          Approve
        </Button>
        <Button
          type="button"
          data-action-id="eval.reject"
          onClick={() => approval.mutate(false)}
        >
          Reject
        </Button>
        <Button type="button" data-action-id="eval.next" onClick={onSelectNext}>
          Next
        </Button>
        <Button
          ref={passagesTrigger}
          type="button"
          data-action-id="eval.passages"
          onClick={onOpenPassages}
        >
          Source preview
        </Button>
      </div>
      <AiTestPanel
        auth={auth}
        caseId={detail.case_id}
        split={detail.split}
        question={question}
        expectedAnswer={answer}
        revealAnswer={revealAnswer}
        onReveal={() => setRevealAnswer(true)}
      />
    </div>
  );
}

type AiTestProps = {
  auth: ApiAuth;
  caseId: string;
  split: string;
  question: string;
  expectedAnswer: string;
  revealAnswer: boolean;
  onReveal: () => void;
};

/**
 * Manual AI test using production Ask. Expected answers stay collapsed.
 *
 * @param props - Case question and gold.
 * @returns AI test controls.
 */
function AiTestPanel({
  auth,
  caseId,
  split,
  question,
  expectedAnswer,
  revealAnswer,
  onReveal,
}: AiTestProps) {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [overlap, setOverlap] = useState<string | null>(null);
  const queries = useChatQueries({
    accessToken: auth.accessToken,
    conversationId,
    runId: null,
    terminal: false,
  });
  const handshake = evaluatePaidHandshake(
    queries.meta ?? null,
    queries.metaPending ? "loading" : queries.metaError ? "error" : "ok",
  );
  const run = useChatRun({
    auth,
    conversationId,
    onConversationId: setConversationId,
    handshake,
    ready: queries.ready,
  });
  const holdout = holdoutCannotRun(split);
  const completed = citationCompareAllowed(run.chat.terminal);
  const compare = useMutation({
    mutationFn: () => comparePdfEvalRun(auth, caseId, run.chat.runId as string),
    onSuccess: (result) => {
      setOverlap(
        `Citation overlap ${String(result.intersection)} of ${String(result.gold_count)} gold IDs (manual AI test, not Recall@10).`,
      );
    },
  });

  return (
    <section aria-label="Manual AI test">
      <h3>AI test</h3>
      <p className={combined.muted}>
        Sends the question only through production Ask. Ranked-ID Recall@10
        remains CLI-only.
      </p>
      {holdout ? (
        <p className={combined.muted}>Holdout cases cannot run from this page.</p>
      ) : (
        <PrimaryAction
          type="button"
          data-action-id="eval.run_ai"
          pending={run.sending}
          pendingLabel="Running…"
          onClick={() => {
            const body = evalAiRequestBody(question);
            void run.send(body.message);
          }}
        >
          Run
        </PrimaryAction>
      )}
      {run.chat.answerText ? (
        <p dir="auto">
          <UserText value={run.chat.answerText} />
        </p>
      ) : null}
      <Button
        type="button"
        data-action-id="eval.reveal_answer"
        disabled={!completed}
        disabledReason={
          completed ? undefined : "Reveal after the AI test completes."
        }
        onClick={onReveal}
      >
        Reveal expected answer
      </Button>
      {revealAnswer && completed ? (
        <p dir="auto">
          <UserText value={expectedAnswer} />
        </p>
      ) : null}
      <Button
        type="button"
        data-action-id="eval.compare"
        disabled={!completed || run.chat.runId === null}
        disabledReason={
          completed ? undefined : "Compare citations after the run completes."
        }
        pending={compare.isPending}
        pendingLabel="Comparing…"
        onClick={() => {
          if (!citationCompareAllowed(run.chat.terminal) || run.chat.runId === null) {
            return;
          }
          compare.mutate();
        }}
      >
        Compare citations
      </Button>
      {overlap ? <p className={combined.muted}>{overlap}</p> : null}
    </section>
  );
}
