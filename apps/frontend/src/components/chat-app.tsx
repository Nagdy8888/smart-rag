/**
 * Auto chat surface at `/`. Handshake, SSE, citations, feedback, usage.
 * Upload and graph live on other routes. GAP-07-01: no route POST field.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { ReadinessPanel, SignedOutageCopy } from "./readiness-panel";
import { Button } from "./ui/button";
import { CitationChip } from "./ui/citation-chip";
import { Drawer } from "./ui/drawer";
import { Input } from "./ui/input";
import { LimitationCallout } from "./ui/limitation-callout";
import { LiveRegion } from "./ui/live-region";
import { LogicalHighlight } from "./ui/logical-highlight";
import { ReviewedContentFixtures } from "./ui/reviewed-content-fixtures";
import { RovingList } from "./ui/roving-list";
import { StatusBanner } from "./ui/status-banner";
import { Textarea } from "./ui/textarea";
import { UserText } from "./ui/user-text";
import {
  cancelRun,
  createConversation,
  deleteConversation,
  fetchMe,
  fetchMeta,
  fetchReady,
  fetchUsageMe,
  listCitations,
  listConversations,
  startOrResumeMessageStream,
  submitFeedback,
  resumeEventStream,
  type ApiAuth,
  type ApiFailure,
} from "../lib/api";
import { MFA_REQUIRED_BANNER, SESSION_REVOKED_BANNER } from "../lib/auth/copy";
import { useSession } from "../lib/auth/session-provider";
import {
  INFERENCE_LINKS_UNAVAILABLE,
  SOURCE_PREVIEW_UNAVAILABLE,
  citationChipHref,
} from "../lib/citation-drawer";
import {
  applyAdmission,
  createChatViewState,
  type ChatViewState,
} from "../lib/chat-view";
import { COMPOSER_MAX_CHARS, composerDraftIsSendable } from "../lib/composer";
import { evaluatePaidHandshake, mayStartPaidPost } from "../lib/handshake";
import { apiFailureBanner, GENERIC_PRODUCTION_ERROR } from "../lib/failure-copy";
import {
  isGraphOnlyInspectionRoute,
  limitationCopy,
  limitationTone,
} from "../lib/limitations";
import { publicQueryKeys, sessionQueryKeys } from "../lib/query-keys";
import { displayText, formatProvenance } from "../lib/safe-text";
import {
  CITATION_LOGICAL_END,
  CITATION_LOGICAL_FIXTURE_TEXT,
  CITATION_LOGICAL_START,
} from "../lib/highlight-logical-range";
import { consumeSse } from "../lib/sse-consume";
import { FEEDBACK_TAGS, type CitationResponse, type ConversationResponse, type FeedbackTag } from "../lib/types";
import styles from "./developer-app.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Render citation ids and provenance in a drawer. No privileged href.
 *
 * @param props - Selected citation or null.
 * @returns Drawer region.
 */
export function CitationDrawer({
  citation,
  onClose,
  returnFocusRef,
}: {
  citation: CitationResponse | null;
  onClose: () => void;
  returnFocusRef?: RefObject<HTMLElement | null>;
}) {
  if (citation === null) {
    return null;
  }
  return (
    <Drawer
      title={`Citation ${String(citation.citation_index)}`}
      onClose={onClose}
      returnFocusRef={returnFocusRef}
    >
      <dl>
        <dt>citation_id</dt>
        <dd>
          <UserText value={citation.citation_id} />
        </dd>
        <dt>chunk_id</dt>
        <dd>
          <UserText value={citation.chunk_id ?? "none"} />
        </dd>
        <dt>provenance</dt>
        <dd>
          <UserText value={formatProvenance(citation.provenance) || "none"} />
        </dd>
      </dl>
      {citation.source_unavailable ? (
        <LimitationCallout tone="warning">
          {limitationCopy("source_unavailable")}
        </LimitationCallout>
      ) : null}
      <p className={styles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
      <section aria-label="Reviewed logical highlight fixture">
        <p className={styles.muted}>
          Citations API has no offset fields. Reviewed logical-offset fixture:
        </p>
        <LogicalHighlight
          text={CITATION_LOGICAL_FIXTURE_TEXT}
          start={CITATION_LOGICAL_START}
          end={CITATION_LOGICAL_END}
        />
      </section>
    </Drawer>
  );
}

/**
 * Auto chat: conversations, composer, transcript, diagnostics, feedback.
 *
 * @returns Chat surface.
 */
export function ChatApp() {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [chat, setChat] = useState<ChatViewState>(() =>
    createChatViewState("00000000-0000-4000-8000-000000000001"),
  );
  const idempotencyRef = useRef<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [feedbackTag, setFeedbackTag] = useState<FeedbackTag>(FEEDBACK_TAGS[0]);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [thumbsUp, setThumbsUp] = useState(true);
  const [selectedCitation, setSelectedCitation] =
    useState<CitationResponse | null>(null);
  const citationTriggerRef = useRef<HTMLElement | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );
  const keys = sessionQueryKeys(accessToken);

  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
  });

  const handshake = evaluatePaidHandshake(
    metaQuery.data ?? null,
    metaQuery.isPending ? "loading" : metaQuery.isError ? "error" : "ok",
  );

  const readyQuery = useQuery({
    queryKey: publicQueryKeys.ready,
    queryFn: () => fetchReady(),
    refetchInterval: 5000,
  });

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const conversationsQuery = useQuery({
    queryKey: keys.conversations,
    queryFn: () => listConversations(auth as ApiAuth),
    enabled: auth !== null,
  });

  const usageQuery = useQuery({
    queryKey: keys.usage,
    queryFn: () => fetchUsageMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const citationsQuery = useQuery({
    queryKey: keys.citations(chat.runId),
    queryFn: () => listCitations(auth as ApiAuth, chat.runId as string),
    enabled: auth !== null && chat.runId !== null && chat.terminal !== null,
  });

  const createMutation = useMutation({
    mutationFn: () => createConversation(auth as ApiAuth, "Chat"),
    onSuccess: (created) => {
      setConversationId(created.conversation_id);
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || conversationId === null) {
        return false;
      }
      return deleteConversation(auth, conversationId);
    },
    onSuccess: (ok) => {
      if (ok) {
        setConversationId(null);
        idempotencyRef.current = newIdempotencyKey();
        setChat(createChatViewState(idempotencyRef.current));
        void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      }
    },
  });

  const send = useCallback(async () => {
    if (auth === null || conversationId === null || !composerDraftIsSendable(draft)) {
      return;
    }
    if (!mayStartPaidPost(handshake, chat)) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    let current = chat;
    if (chat.runId === null || chat.terminal !== null) {
      if (idempotencyRef.current === null) {
        idempotencyRef.current = newIdempotencyKey();
      }
      current = createChatViewState(idempotencyRef.current);
      setChat(current);
      setFailure(null);
    }
    const started = await startOrResumeMessageStream(
      auth,
      conversationId,
      draft,
      {
        runId: current.runId,
        terminal: current.terminal,
        lastSequence: current.lastSequence,
        idempotencyKey: current.idempotencyKey,
      },
    );
    if (started.failure) {
      setFailure(started.failure);
      return;
    }
    if (started.admission !== null) {
      current = applyAdmission(current, {
        run_id: started.admission.run_id,
        reservation_id: started.admission.reservation_id,
        route_family: started.admission.route_family,
        reconnect: started.admission.reconnect,
      });
      setChat(current);
    }
    current = await consumeSse(started.response, current, controller.signal, setChat);
    setChat(current);
    if (current.terminal !== null) {
      idempotencyRef.current = newIdempotencyKey();
      setChat((prev) => ({
        ...prev,
        idempotencyKey: idempotencyRef.current as string,
      }));
    }
  }, [auth, chat, conversationId, draft, handshake]);

  const reconnect = useCallback(async () => {
    if (auth === null || chat.runId === null) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const response = await resumeEventStream(auth, chat.runId, chat.lastSequence);
    if (response.status === 404) {
      setFailure({ kind: "deleted" });
      return;
    }
    const current = await consumeSse(response, chat, controller.signal, setChat);
    setChat(current);
  }, [auth, chat]);

  const cancel = useCallback(async () => {
    abortRef.current?.abort();
    if (auth !== null && chat.runId !== null) {
      await cancelRun(auth, chat.runId);
    }
  }, [auth, chat.runId]);

  const sendFeedback = useCallback(async () => {
    if (auth === null || chat.runId === null) {
      return;
    }
    await submitFeedback(
      auth,
      chat.runId,
      thumbsUp,
      feedbackTag,
      feedbackComment || null,
    );
  }, [auth, chat.runId, feedbackComment, feedbackTag, thumbsUp]);

  const mfaRequired =
    meQuery.isError &&
    meQuery.error instanceof Error &&
    meQuery.error.message === "mfa_required";

  const sessionRevoked =
    meQuery.isError &&
    meQuery.error instanceof Error &&
    meQuery.error.message === "session_revoked";

  useEffect(() => {
    if (sessionRevoked) {
      void session.signOut();
    }
  }, [session, sessionRevoked]);

  const paradeDbDown =
    readyQuery.data?.dependencies.some(
      (item) => item.name === "paradedb" && item.status === "down",
    ) === true;
  const bm25Limitation =
    chat.diagnostics.limitationCodes.includes("bm25_unavailable");

  const assertiveCopy = (() => {
    if (failure?.kind === "upgrade" || failure?.kind === "budget") {
      return apiFailureBanner(failure);
    }
    if (mfaRequired) {
      return MFA_REQUIRED_BANNER;
    }
    if (chat.terminal === "error") {
      return GENERIC_PRODUCTION_ERROR;
    }
    return "";
  })();

  if (!session.ready) {
    return (
      <div className={styles.shell}>
        <h1>Auto chat</h1>
        <p className={styles.muted}>Restoring session.</p>
      </div>
    );
  }

  if (accessToken === null) {
    return (
      <div className={styles.shell}>
        <h1>Auto chat</h1>
        <StatusBanner kind="info" role="status">
          Sign in to continue. Optimistic cookie checks are not authorization.
        </StatusBanner>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
        <ReadinessPanel ready={readyQuery.data} />
        <SignedOutageCopy />
        <ReviewedContentFixtures />
      </div>
    );
  }

  if (mfaRequired) {
    return (
      <div className={styles.shell}>
        <header className={styles.row}>
          <h1>Auto chat</h1>
          <Button type="button" onClick={() => void session.signOut()}>
            Sign out
          </Button>
        </header>
        <StatusBanner kind="error" role="alert">
          {MFA_REQUIRED_BANNER}
        </StatusBanner>
        <LiveRegion politeness="assertive" aria-label="Blocking errors">
          {MFA_REQUIRED_BANNER}
        </LiveRegion>
        <p className={styles.muted}>
          <Link href="/mfa/challenge">MFA challenge</Link>
          {" · "}
          <Link href="/mfa/enroll">Enroll TOTP</Link>
        </p>
        <ReadinessPanel ready={readyQuery.data} />
      </div>
    );
  }

  if (sessionRevoked || (failure?.kind === "auth" && failure.detail === "session_revoked")) {
    return (
      <div className={styles.shell}>
        <h1>Auto chat</h1>
        <StatusBanner kind="error" role="alert">
          {SESSION_REVOKED_BANNER}
        </StatusBanner>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const sendDisabled =
    !mayStartPaidPost(handshake, chat) ||
    !composerDraftIsSendable(draft) ||
    conversationId === null;

  return (
    <div className={styles.shell}>
      <header className={styles.row}>
        <h1>Auto chat</h1>
        <p className={styles.muted} data-testid="auto-label">
          Auto (server-routed). This label does not change the POST body.
        </p>
        <p className={styles.muted}>
          Signed in as <UserText value={meQuery.data?.role ?? "unknown"} />{" "}
          <UserText value={meQuery.data?.user_id ?? ""} />
        </p>
        <Button type="button" onClick={() => void session.signOut()}>
          Sign out
        </Button>
      </header>

      <HandshakeBanner />

      {failure ? (
        <StatusBanner
          kind={failure.kind === "deleted" ? "info" : "error"}
          role={failure.kind === "deleted" ? "status" : "alert"}
        >
          {apiFailureBanner(failure)}
        </StatusBanner>
      ) : null}

      <LiveRegion politeness="assertive" aria-label="Blocking errors">
        {assertiveCopy || ""}
      </LiveRegion>

      {deleteMutation.isSuccess && failure?.kind !== "deleted" ? (
        <StatusBanner kind="info" role="status">
          Conversation deleted. Reads, resume, and citations are denied. No
          source text is shown.
        </StatusBanner>
      ) : null}

      <div className={styles.grid}>
        <aside className={styles.panel}>
          <h2>Conversations</h2>
          <div className={styles.row}>
            <Button type="button" onClick={() => createMutation.mutate()}>
              New conversation
            </Button>
            <Button
              type="button"
              onClick={() => deleteMutation.mutate()}
              disabled={conversationId === null}
            >
              Delete conversation
            </Button>
          </div>
          {conversationsQuery.isPending ? (
            <p className={styles.muted}>Loading conversations</p>
          ) : null}
          {(conversationsQuery.data ?? []).length === 0 &&
          !conversationsQuery.isPending ? (
            <p className={styles.muted}>No conversations yet</p>
          ) : null}
          <RovingList
            aria-label="Conversations"
            className={styles.list}
            selectedId={conversationId}
            items={(conversationsQuery.data ?? []).map(
              (item: ConversationResponse) => ({
                id: item.conversation_id,
                item,
              }),
            )}
            onSelect={(item) => {
              setConversationId(item.conversation_id);
              idempotencyRef.current = newIdempotencyKey();
              setChat(createChatViewState(idempotencyRef.current));
              setFailure(null);
            }}
          >
            {(item) => (
              <UserText value={item.title ?? item.conversation_id} />
            )}
          </RovingList>
        </aside>

        <section className={styles.panel} aria-label="Auto chat">
          <p className={styles.muted}>
            SubmitMessageRequest is message plus optional idempotency_key only.
            Hybrid/Combined/Table/Inspect send controls are not present
            (GAP-07-01).
          </p>
          <Textarea
            label="Message"
            rows={4}
            maxLength={COMPOSER_MAX_CHARS}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={!mayStartPaidPost(handshake, chat)}
          />
          <div className={styles.row}>
            <Button
              type="button"
              variant="primary"
              onClick={() => void send()}
              disabled={sendDisabled}
            >
              Send
            </Button>
            <Button type="button" onClick={() => void reconnect()}>
              Reconnect
            </Button>
            <Button type="button" onClick={() => void cancel()}>
              Cancel
            </Button>
          </div>
          <LiveRegion aria-label="Answer tokens" politeness="polite">
            <UserText value={chat.answerText || "No tokens yet."} />
          </LiveRegion>
          {isGraphOnlyInspectionRoute(
            chat.diagnostics.effectiveRoute ?? chat.routeFamily,
          ) ? (
            <LimitationCallout tone="warning">
              Graph-only inspection is not an answering mode. Final answers use
              Hybrid evidence.
            </LimitationCallout>
          ) : null}

          <details className={styles.diagnostics} data-testid="advanced-diagnostics">
            <summary>Advanced (requested vs effective route)</summary>
            <dl>
              <dt>Requested route</dt>
              <dd>
                <UserText
                  value={
                    chat.diagnostics.requestedRoute ?? chat.routeFamily ?? "—"
                  }
                />
              </dd>
              <dt>Effective route</dt>
              <dd>
                <UserText value={chat.diagnostics.effectiveRoute ?? "—"} />
              </dd>
              <dt>Corrected route</dt>
              <dd>
                <UserText value={chat.diagnostics.correctedRoute ?? "none"} />
              </dd>
              <dt>Correction reason</dt>
              <dd>
                <UserText value={chat.diagnostics.correctionReason ?? "—"} />
              </dd>
              <dt>Cache</dt>
              <dd>
                <UserText value={chat.diagnostics.cacheStatus ?? "—"} />
              </dd>
              <dt>Coverage</dt>
              <dd>
                {chat.diagnostics.coverageScore === null
                  ? "—"
                  : String(chat.diagnostics.coverageScore)}
              </dd>
              <dt>Tools</dt>
              <dd>
                <UserText
                  value={chat.diagnostics.toolKeys.map(displayText).join(", ") || "none"}
                />
              </dd>
              <dt>Heartbeats</dt>
              <dd>{String(chat.diagnostics.heartbeatCount)}</dd>
              <dt>Unknown events</dt>
              <dd>
                {chat.diagnostics.unknownEvents.join(", ") || "none (ignored)"}
              </dd>
              <dt>Stage</dt>
              <dd>
                <UserText value={chat.stage ?? "—"} /> /{" "}
                <UserText value={chat.status ?? "—"} />
              </dd>
              <dt>Terminal</dt>
              <dd>
                <UserText value={chat.terminal ?? "running"} />
              </dd>
            </dl>
            <p className={styles.muted}>{INFERENCE_LINKS_UNAVAILABLE}</p>
          </details>

          {chat.diagnostics.limitationCodes.map((code) => (
            <LimitationCallout key={code} tone={limitationTone(code)}>
              {limitationCopy(code)}
            </LimitationCallout>
          ))}
          {paradeDbDown ? (
            <LimitationCallout tone="warning">
              {limitationCopy("bm25_unavailable")}
            </LimitationCallout>
          ) : null}
          {paradeDbDown && bm25Limitation ? (
            <p className={styles.muted}>
              Ready ParadeDB is down and the run reported bm25_unavailable. BM25
              is not claimed healthy.
            </p>
          ) : null}

          <ReadinessPanel ready={readyQuery.data} />
          <SignedOutageCopy />

          <p className={styles.muted} data-testid="usage-strip">
            Usage {String(chat.diagnostics.promptTokens)}/
            {String(chat.diagnostics.completionTokens)} tokens. Company total{" "}
            {String(usageQuery.data?.cost_usd ?? "—")} USD.
          </p>

          <h2>Citations</h2>
          <ul className={styles.list}>
            {(citationsQuery.data ?? []).map((citation) => (
              <li key={citation.citation_id}>
                <CitationChip
                  index={citation.citation_index}
                  citationId={citation.citation_id}
                  unavailable={citation.source_unavailable}
                  href={citationChipHref(citation.provenance.url)}
                  onSelect={(trigger) => {
                    citationTriggerRef.current = trigger;
                    setSelectedCitation(citation);
                  }}
                />
              </li>
            ))}
          </ul>
          <CitationDrawer
            citation={selectedCitation}
            onClose={() => setSelectedCitation(null)}
            returnFocusRef={citationTriggerRef}
          />

          <ReviewedContentFixtures />

          <h2>Feedback</h2>
          <div className={styles.row}>
            <Button
              type="button"
              variant={thumbsUp ? "primary" : "secondary"}
              onClick={() => setThumbsUp(true)}
            >
              Thumbs up
            </Button>
            <Button
              type="button"
              variant={!thumbsUp ? "primary" : "secondary"}
              onClick={() => setThumbsUp(false)}
            >
              Thumbs down
            </Button>
          </div>
          <label>
            Tag
            <select
              value={feedbackTag}
              onChange={(event) =>
                setFeedbackTag(event.target.value as FeedbackTag)
              }
            >
              {FEEDBACK_TAGS.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
          </label>
          <Input
            label="Comment"
            value={feedbackComment}
            onChange={(event) => setFeedbackComment(event.target.value)}
          />
          <Button type="button" onClick={() => void sendFeedback()}>
            Submit feedback
          </Button>
        </section>
      </div>
    </div>
  );
}
