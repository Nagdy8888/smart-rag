/**
 * Manual production Ask test. Expected answers stay collapsed.
 */

"use client";

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { comparePdfEvalRun, type ApiAuth } from "../../lib/api";
import {
  citationCompareAllowed,
  evalAiRequestBody,
  holdoutCannotRun,
} from "../../lib/eval-workspace";
import { evaluatePaidHandshake } from "../../lib/handshake";
import { Button, PrimaryAction } from "../ui/button";
import { UserText } from "../ui/user-text";
import { useChatQueries } from "../chat/hooks/use-chat-queries";
import { useChatRun } from "../chat/hooks/use-chat-run";
import styles from "./evaluation.module.css";

export type EvaluationAiTestPanelProps = {
  /** Owner/admin bearer auth. */
  auth: ApiAuth;
  /** Case under test. */
  caseId: string;
  /** Case split. Holdout cannot run. */
  split: string;
  /** Question only. */
  question: string;
  /** Expected answer revealed after a completed run. */
  expectedAnswer: string;
  /** Whether the expected answer is revealed. */
  revealAnswer: boolean;
  /** Reveal the expected answer. */
  onReveal: () => void;
};

/**
 * Run the question through production Ask. Citation overlap is not Recall@10.
 *
 * @param props - Case question and gold.
 * @returns Manual test controls.
 */
export function EvaluationAiTestPanel({
  auth,
  caseId,
  split,
  question,
  expectedAnswer,
  revealAnswer,
  onReveal,
}: EvaluationAiTestPanelProps) {
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
        `Cited ${String(result.intersection)} of ${String(result.gold_count)} required sources.`,
      );
    },
  });

  return (
    <section className={styles.section} aria-label="Test this case">
      <h3>Test this case</h3>
      <p className={styles.muted}>
        Run the question through production Ask. The expected answer is not sent
        to the model.
      </p>
      {holdout ? (
        <p className={styles.muted}>Holdout cases cannot run from this page.</p>
      ) : (
        <PrimaryAction
          type="button"
          data-action-id="eval.run_ai"
          pending={run.sending}
          pendingLabel="Running test…"
          onClick={() => {
            const body = evalAiRequestBody(question);
            void run.send(body.message);
          }}
        >
          Run test
        </PrimaryAction>
      )}
      {run.chat.answerText ? (
        <div className={styles.answerSurface} dir="auto">
          <UserText value={run.chat.answerText} />
        </div>
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
        <div className={styles.answerSurface} dir="auto">
          <UserText value={expectedAnswer} />
        </div>
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
        Compare cited sources
      </Button>
      <p className={styles.muted}>
        This compares cited source IDs for this one answer. It is not official
        Recall@10.
      </p>
      {overlap ? <p className={styles.muted}>{overlap}</p> : null}
    </section>
  );
}
