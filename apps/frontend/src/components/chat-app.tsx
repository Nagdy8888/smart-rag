/**
 * Auto chat surface at `/`. Handshake, SSE, citations, feedback, usage.
 * Upload and graph live on other routes. GAP-07-01: no route POST field.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { HandshakeBanner } from "./auth/auth-screens";
import { Button } from "./ui/button";
import { Drawer } from "./ui/drawer";
import { LimitationCallout } from "./ui/limitation-callout";
import { LiveRegion } from "./ui/live-region";
import { StatusBanner } from "./ui/status-banner";
import { UserText } from "./ui/user-text";
import {
  cancelRun,
  createConversation,
  deleteConversation,
  fetchMe,
  fetchMeta,
  loadConsoleReadiness,
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
  SOURCE_PREVIEW_UNAVAILABLE,
  citationChipHref,
} from "../lib/citation-drawer";
import {
  applyAdmission,
  createChatViewState,
  type ChatViewState,
} from "../lib/chat-view";
import { composerDraftIsSendable } from "../lib/composer";
import { evaluatePaidHandshake, mayStartPaidPost } from "../lib/handshake";
import { apiFailureBanner, GENERIC_PRODUCTION_ERROR } from "../lib/failure-copy";
import {
  isGraphOnlyInspectionRoute,
  limitationCopy,
  limitationTone,
} from "../lib/limitations";
import { publicQueryKeys, sessionQueryKeys } from "../lib/query-keys";
import { formatProvenance } from "../lib/safe-text";
import { consumeSse, isAbortError } from "../lib/sse-consume";
import {
  MAX_RECONNECT_ATTEMPTS,
  reconnectDelayMs,
  shouldStopReconnect,
  waitForReconnectDelay,
} from "../lib/stream-reconnect";
import { FEEDBACK_TAGS, type CitationResponse, type FeedbackTag } from "../lib/types";
import { AnswerSurface } from "./chat/answer-surface";
import { ChatComposer } from "./chat/chat-composer";
import { ChatWorkspace } from "./chat/chat-workspace";
import { CitationSheet } from "./chat/citation-sheet";
import { ConversationRail } from "./chat/conversation-rail";
import { FeedbackPopover } from "./chat/feedback-popover";
import { RunDetailsSheet } from "./chat/run-details-sheet";
import { RunProgress } from "./chat/run-progress";
import { Sheet } from "./ui/sheet";
import chatStyles from "./chat/chat.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Render citation ids and provenance in a drawer. No privileged href and
 * no ACME logical-offset fixture. Offsets are GAP-07-09 until the citations
 * API returns them. Logical highlight lives on `ReviewedContentFixtures`.
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
      <p className={chatStyles.muted}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
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
  const [lastUserMessage, setLastUserMessage] = useState("");
  const citationTriggerRef = useRef<HTMLElement | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [conversationsOpen, setConversationsOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const sendLockRef = useRef(false);
  const autoResumeRef = useRef<((currentChat: ChatViewState, controller: AbortController) => Promise<void>) | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);
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
    queryKey: auth === null ? publicQueryKeys.ready : keys.consoleReady,
    queryFn: () => loadConsoleReadiness(auth),
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

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const send = useCallback(async () => {
    if (sendLockRef.current) {
      return;
    }
    if (auth === null || !composerDraftIsSendable(draft)) {
      return;
    }
    if (!mayStartPaidPost(handshake, chat)) {
      return;
    }
    sendLockRef.current = true;
    let activeConversationId = conversationId;
    if (activeConversationId === null) {
      try {
        const created = await createConversation(auth, "Chat");
        activeConversationId = created.conversation_id;
        setConversationId(created.conversation_id);
        void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      } catch {
        setFailure({ kind: "server", status: 500 });
        sendLockRef.current = false;
        return;
      }
    }
    setLastUserMessage(draft.trim());
    setDisconnected(false);
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
    try {
      const started = await startOrResumeMessageStream(
        auth,
        activeConversationId,
        draft,
        {
          runId: current.runId,
          terminal: current.terminal,
          lastSequence: current.lastSequence,
          idempotencyKey: current.idempotencyKey,
        },
        fetch,
        controller.signal,
      );
      if (controller.signal.aborted) {
        return;
      }
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
      current = await consumeSse(
        started.response,
        current,
        controller.signal,
        setChat,
      );
      if (controller.signal.aborted) {
        setChat(current);
        return;
      }
      setChat(current);
      if (current.terminal !== null) {
        idempotencyRef.current = newIdempotencyKey();
        setChat((prev) => ({
          ...prev,
          idempotencyKey: idempotencyRef.current as string,
        }));
      } else if (!controller.signal.aborted) {
        setDisconnected(true);
        void autoResumeRef.current?.(current, controller);
      }
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) {
        return;
      }
      setDisconnected(true);
      void autoResumeRef.current?.(chat, controller);
    } finally {
      sendLockRef.current = false;
    }
  }, [auth, chat, conversationId, draft, handshake, queryClient]);

  const resumeOnce = useCallback(
    async (currentChat: ChatViewState, controller: AbortController) => {
      if (auth === null || currentChat.runId === null) {
        return null;
      }
      const response = await resumeEventStream(
        auth,
        currentChat.runId,
        currentChat.lastSequence,
        fetch,
        controller.signal,
      );
      if (controller.signal.aborted) {
        return null;
      }
      if (response.status === 404) {
        setFailure({ kind: "deleted" });
        return "deleted" as const;
      }
      const current = await consumeSse(
        response,
        currentChat,
        controller.signal,
        setChat,
      );
      setChat(current);
      return current;
    },
    [auth],
  );

  const autoResume = useCallback(
    async (currentChat: ChatViewState, controller: AbortController) => {
      let latest = currentChat;
      for (let attemptIndex = 0; attemptIndex < MAX_RECONNECT_ATTEMPTS; attemptIndex += 1) {
        const stop = shouldStopReconnect({
          attemptIndex,
          cancelled: controller.signal.aborted,
          terminal: latest.terminal,
          signedOut: auth === null,
          runDeleted: failure?.kind === "deleted",
          unmounted: !mountedRef.current,
        });
        if (stop !== null) {
          return;
        }
        try {
          await waitForReconnectDelay(reconnectDelayMs(attemptIndex), controller.signal);
        } catch {
          return;
        }
        try {
          const resumed = await resumeOnce(latest, controller);
          if (resumed === "deleted" || resumed === null) {
            return;
          }
          latest = resumed;
          if (latest.terminal !== null) {
            setDisconnected(false);
            return;
          }
        } catch (error) {
          if (controller.signal.aborted || isAbortError(error)) {
            return;
          }
        }
      }
      setDisconnected(true);
    },
    [auth, failure?.kind, resumeOnce],
  );

  useEffect(() => {
    autoResumeRef.current = autoResume;
  }, [autoResume]);

  const reconnect = useCallback(async () => {
    if (auth === null || chat.runId === null) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setDisconnected(false);
    try {
      const resumed = await resumeOnce(chat, controller);
      if (resumed === "deleted" || resumed === null) {
        return;
      }
      if (resumed.terminal === null && !controller.signal.aborted) {
        setDisconnected(true);
        void autoResumeRef.current?.(resumed, controller);
      }
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) {
        return;
      }
      setDisconnected(true);
    }
  }, [auth, chat, resumeOnce]);

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
    try {
      await submitFeedback(
        auth,
        chat.runId,
        thumbsUp,
        feedbackTag,
        feedbackComment || null,
      );
      setFeedbackStatus("Feedback recorded.");
    } catch {
      setFeedbackStatus("Feedback could not be recorded.");
    }
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
      <div className={chatStyles.page}>
        <h2>Auto chat</h2>
        <p className={chatStyles.muted}>Restoring session.</p>
      </div>
    );
  }

  if (accessToken === null) {
    return (
      <div className={chatStyles.page}>
        <h2>Auto chat</h2>
        <StatusBanner kind="info" role="status">
          Sign in to continue.
        </StatusBanner>
        <p className={chatStyles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  if (mfaRequired) {
    return (
      <div className={chatStyles.page}>
        <header className={chatStyles.header}>
          <h2>Auto chat</h2>
          <Button type="button" onClick={() => void session.signOut()}>
            Sign out
          </Button>
        </header>
        <StatusBanner kind="error" role="alert">
          {MFA_REQUIRED_BANNER}
        </StatusBanner>
        <LiveRegion politeness="assertive" aria-label="Blocking errors" visuallyHidden>
          {MFA_REQUIRED_BANNER}
        </LiveRegion>
        <p className={chatStyles.muted}>
          <Link href="/mfa/challenge">MFA challenge</Link>
          {" · "}
          <Link href="/mfa/enroll">Enroll TOTP</Link>
        </p>
      </div>
    );
  }

  if (sessionRevoked || (failure?.kind === "auth" && failure.detail === "session_revoked")) {
    return (
      <div className={chatStyles.page}>
        <h2>Auto chat</h2>
        <StatusBanner kind="error" role="alert">
          {SESSION_REVOKED_BANNER}
        </StatusBanner>
        <p className={chatStyles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const sendDisabled =
    !mayStartPaidPost(handshake, chat) ||
    !composerDraftIsSendable(draft);

  const citations = citationsQuery.data ?? [];
  const companyUsd = String(usageQuery.data?.cost_usd ?? "—");

  const rail = (
    <ConversationRail
      conversations={conversationsQuery.data ?? []}
      selectedId={conversationId}
      loading={conversationsQuery.isPending}
      onCreate={() => createMutation.mutate()}
      onSelect={(item) => {
        setConversationId(item.conversation_id);
        idempotencyRef.current = newIdempotencyKey();
        setChat(createChatViewState(idempotencyRef.current));
        setFailure(null);
        setLastUserMessage("");
      }}
      onDelete={() => deleteMutation.mutate()}
    />
  );

  const stage = (
    <section className={chatStyles.stage} aria-label="Auto chat">
      <div className={chatStyles.stageHeader}>
        <p className={chatStyles.historyNote}>
          This view shows the current run only. Earlier turns are not loaded.
        </p>
        <div className={chatStyles.row}>
          <Button type="button" variant="ghost" onClick={() => setSourcesOpen(true)}>
            Sources ({String(citations.length)})
          </Button>
          <RunDetailsSheet
            open={detailsOpen}
            onOpen={() => setDetailsOpen(true)}
            onClose={() => setDetailsOpen(false)}
            chat={chat}
            companyUsd={companyUsd}
          />
        </div>
      </div>
      <RunProgress chat={chat} />
      <AnswerSurface
        question={lastUserMessage}
        answer={chat.answerText}
        citations={citations}
        terminal={chat.terminal}
        hrefForCitation={(citation) => citationChipHref(citation.provenance.url) ?? undefined}
        onSelectCitation={(citation, trigger) => {
          citationTriggerRef.current = trigger;
          setSelectedCitation(citation);
        }}
      />
      {isGraphOnlyInspectionRoute(
        chat.diagnostics.effectiveRoute ?? chat.routeFamily,
      ) ? (
        <LimitationCallout tone="warning">
          Graph-only inspection is not an answering mode. Final answers use
          Hybrid evidence.
        </LimitationCallout>
      ) : null}
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
        <p className={chatStyles.muted}>
          Search is degraded. Keyword retrieval is not claimed healthy.
        </p>
      ) : null}
      <FeedbackPopover
        thumbsUp={thumbsUp}
        onThumbs={setThumbsUp}
        tag={feedbackTag}
        onTag={setFeedbackTag}
        comment={feedbackComment}
        onComment={setFeedbackComment}
        onSubmit={() => void sendFeedback()}
      />
      <ChatComposer
        value={draft}
        onChange={setDraft}
        onSend={() => void send()}
        onCancel={() => void cancel()}
        onReconnect={() => void reconnect()}
        sendDisabled={sendDisabled}
        running={chat.terminal === null && chat.runId !== null}
      />
    </section>
  );

  return (
    <div className={chatStyles.page}>
      <header className={chatStyles.header}>
        <div>
          <h2>Auto chat</h2>
          <p className={chatStyles.lead}>Ask across authorized documents. Routing is automatic.</p>
        </div>
        <span className={chatStyles.autoChip} data-testid="auto-label">
          Auto
        </span>
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

      {disconnected && chat.terminal === null ? (
        <StatusBanner kind="warning" role="status">
          The stream disconnected. Automatic resume uses the same run. Use
          Reconnect if it does not recover.
        </StatusBanner>
      ) : null}

      {feedbackStatus ? (
        <StatusBanner kind="info" role="status">
          {feedbackStatus}
        </StatusBanner>
      ) : null}

      <LiveRegion politeness="assertive" aria-label="Blocking errors" visuallyHidden>
        {assertiveCopy || ""}
      </LiveRegion>

      {deleteMutation.isSuccess && failure?.kind !== "deleted" ? (
        <StatusBanner kind="info" role="status">
          Conversation deleted. Reads, resume, and citations are denied. No
          source text is shown.
        </StatusBanner>
      ) : null}

      <div className={chatStyles.mobileBar}>
        <Button type="button" variant="secondary" onClick={() => setConversationsOpen(true)}>
          Conversations
        </Button>
        <Button type="button" variant="ghost" onClick={() => setSourcesOpen(true)}>
          Sources
        </Button>
      </div>

      <ChatWorkspace
        rail={rail}
        stage={stage}
        sources={
          <div className={chatStyles.sourcesPane}>
            <h2>Sources</h2>
            <p className={chatStyles.hint}>{SOURCE_PREVIEW_UNAVAILABLE}</p>
          </div>
        }
      />

      {conversationsOpen ? (
        <Sheet title="Conversations" side="left" onClose={() => setConversationsOpen(false)}>
          {rail}
        </Sheet>
      ) : null}

      <CitationSheet
        open={sourcesOpen}
        onClose={() => setSourcesOpen(false)}
        citations={citations}
        hrefForCitation={(citation) => citationChipHref(citation.provenance.url) ?? undefined}
        onSelectCitation={(citation, trigger) => {
          citationTriggerRef.current = trigger;
          setSelectedCitation(citation);
          setSourcesOpen(false);
        }}
      />

      <CitationDrawer
        citation={selectedCitation}
        onClose={() => setSelectedCitation(null)}
        returnFocusRef={citationTriggerRef}
      />
    </div>
  );
}
