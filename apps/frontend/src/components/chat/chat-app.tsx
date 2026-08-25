/**
 * Ask surface at `/`. Handshake, SSE, citations, feedback, usage.
 * Upload and graph live on other routes. GAP-07-01: no route POST field.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from "react";
import { conversationTitleFromPrompt } from "../../lib/conversation-title";
import {
  SESSIONS_EXPANDED_STORAGE_KEY,
  readBooleanPreference,
  writeBooleanPreference,
} from "../../lib/layout-preferences";
import { HandshakeBanner } from "../auth/auth-screens";
import { Button } from "../ui/button";
import { Icon } from "../ui/icon";
import { Drawer } from "../ui/drawer";
import { LimitationCallout } from "../ui/limitation-callout";
import { LiveRegion } from "../ui/live-region";
import { StatusBanner } from "../ui/status-banner";
import { UserText } from "../ui/user-text";
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
  fetchConversation,
  fetchRun,
  isClassifiedApiError,
  type ApiAuth,
  type ApiFailure,
} from "../../lib/api";
import { SESSION_REVOKED_BANNER } from "../../lib/auth/copy";
import { useSession } from "../../lib/auth/session-provider";
import {
  SOURCE_PREVIEW_UNAVAILABLE,
  citationChipHref,
} from "../../lib/citation-drawer";
import {
  applyAdmission,
  createChatViewState,
  shouldShowChatFailureBanner,
  type ChatViewState,
} from "../../lib/chat-view";
import {
  clearChatRunPointer,
  isActiveRunStatus,
  readChatRunPointer,
  writeChatRunPointer,
} from "../../lib/chat-pointer";
import { composerDraftIsSendable } from "../../lib/composer";
import {
  evaluatePaidHandshake,
  paidSendBlockReason,
} from "../../lib/handshake";
import {
  apiFailureBanner,
  chatRunFailureBanner,
  GENERIC_PRODUCTION_ERROR,
} from "../../lib/failure-copy";
import {
  isGraphOnlyInspectionRoute,
  limitationCopy,
  limitationTone,
} from "../../lib/limitations";
import { publicQueryKeys, sessionQueryKeys } from "../../lib/query-keys";
import { formatProvenance } from "../../lib/safe-text";
import { consumeSse, isAbortError } from "../../lib/sse-consume";
import {
  MAX_RECONNECT_ATTEMPTS,
  reconnectDelayMs,
  shouldStopReconnect,
  waitForReconnectDelay,
} from "../../lib/stream-reconnect";
import { FEEDBACK_TAGS, type CitationResponse, type ConversationResponse, type FeedbackTag } from "../../lib/types";
import { AnswerSurface } from "./answer-surface";
import { ChatComposer } from "./chat-composer";
import { ChatWorkspace } from "./chat-workspace";
import { CitationSheet } from "./citation-sheet";
import { ConversationRail } from "./conversation-rail";
import { FeedbackPopover } from "./feedback-popover";
import { RunDetailsSheet } from "./run-details-sheet";
import { RunProgress } from "./run-progress";
import { Sheet } from "../ui/sheet";
import chatStyles from "./chat.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

const PROMPT_CHIPS = [
  "Summarize an uploaded policy",
  "Compare two documented values",
  "Find a relationship between entities",
] as const;

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
 * Ask: sessions, composer, transcript, diagnostics, feedback.
 *
 * @returns Chat surface. The Sessions list and conversation body scroll
 *   independently; the Sessions header and composer stay pinned. New
 *   sessions take their title from the first prompt.
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
  const [conversationsOpen, setSessionsOpen] = useState(false);
  const [sessionsExpanded, setSessionsExpanded] = useState(() =>
    readBooleanPreference(SESSIONS_EXPANDED_STORAGE_KEY, true),
  );
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const sendLockRef = useRef(false);
  const autoResumeRef = useRef<((currentChat: ChatViewState, controller: AbortController) => Promise<void>) | null>(null);
  const [disconnected, setDisconnected] = useState(false);
  const [feedbackStatus, setFeedbackStatus] = useState<string | null>(null);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [reconnectExhausted, setReconnectExhausted] = useState(false);
  const [nextRetryMs, setNextRetryMs] = useState<number | null>(null);
  const recoveredRef = useRef(false);
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

  const resetClientChat = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    clearChatRunPointer();
    sendLockRef.current = false;
    idempotencyRef.current = newIdempotencyKey();
    setConversationId(null);
    setDraft("");
    setChat(createChatViewState(idempotencyRef.current));
    setFailure(null);
    setLastUserMessage("");
    setDisconnected(false);
    setReconnectAttempt(0);
    setReconnectExhausted(false);
    setNextRetryMs(null);
  }, []);

  /**
   * Toggle the desktop Sessions column and persist the choice.
   */
  function toggleSessionsExpanded(): void {
    setSessionsExpanded((current) => {
      const next = !current;
      writeBooleanPreference(SESSIONS_EXPANDED_STORAGE_KEY, next);
      return next;
    });
  }

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || conversationId === null) {
        return false;
      }
      return deleteConversation(auth, conversationId);
    },
    onSuccess: (ok) => {
      if (ok) {
        resetClientChat();
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
    if (paidSendBlockReason(handshake, readyQuery.data ?? null, chat) !== null) {
      return;
    }
    sendLockRef.current = true;
    let activeConversationId = conversationId;
    if (activeConversationId === null) {
      try {
        const created = await createConversation(
          auth,
          conversationTitleFromPrompt(draft),
        );
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
    setReconnectAttempt(0);
    setReconnectExhausted(false);
    setNextRetryMs(null);
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
        setDraft("");
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
  }, [auth, chat, conversationId, draft, handshake, queryClient, readyQuery.data]);

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
      setReconnectExhausted(false);
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
        setReconnectAttempt(attemptIndex + 1);
        const delay = reconnectDelayMs(attemptIndex);
        setNextRetryMs(delay);
        try {
          await waitForReconnectDelay(delay, controller.signal);
        } catch {
          return;
        }
        setNextRetryMs(null);
        try {
          const resumed = await resumeOnce(latest, controller);
          if (resumed === "deleted" || resumed === null) {
            return;
          }
          latest = resumed;
          if (latest.terminal !== null) {
            setDisconnected(false);
            setReconnectAttempt(0);
            setReconnectExhausted(false);
            setNextRetryMs(null);
            return;
          }
        } catch (error) {
          if (controller.signal.aborted || isAbortError(error)) {
            return;
          }
        }
      }
      setDisconnected(true);
      setReconnectExhausted(true);
      setNextRetryMs(null);
    },
    [auth, failure?.kind, resumeOnce],
  );

  useEffect(() => {
    autoResumeRef.current = autoResume;
  }, [autoResume]);

  useEffect(() => {
    if (conversationId !== null && chat.runId !== null && chat.terminal === null) {
      writeChatRunPointer({
        conversationId,
        runId: chat.runId,
        lastSequence: chat.lastSequence,
      });
      return;
    }
    if (chat.terminal !== null) {
      clearChatRunPointer();
    }
  }, [chat.lastSequence, chat.runId, chat.terminal, conversationId]);

  useEffect(() => {
    if (auth === null || recoveredRef.current) {
      return;
    }
    const pointer = readChatRunPointer();
    if (pointer === null) {
      recoveredRef.current = true;
      return;
    }
    recoveredRef.current = true;
    let cancelled = false;
    const controller = new AbortController();
    abortRef.current = controller;
    void (async () => {
      try {
        const conversation = await fetchConversation(auth, pointer.conversationId);
        if (cancelled || controller.signal.aborted) {
          return;
        }
        const run = await fetchRun(auth, pointer.runId);
        if (cancelled || controller.signal.aborted) {
          return;
        }
        if (run.conversation_id !== conversation.conversation_id) {
          clearChatRunPointer();
          return;
        }
        if (!isActiveRunStatus(run.status)) {
          clearChatRunPointer();
          return;
        }
        setConversationId(pointer.conversationId);
        const recovered = {
          ...createChatViewState(idempotencyRef.current ?? newIdempotencyKey()),
          runId: run.run_id,
          lastSequence: pointer.lastSequence,
          reservationId: run.reservation_id,
        };
        setChat(recovered);
        const resumed = await resumeOnce(recovered, controller);
        if (resumed === "deleted" || resumed === null || cancelled) {
          return;
        }
        if (resumed.terminal === null && !controller.signal.aborted) {
          setDisconnected(true);
          void autoResumeRef.current?.(resumed, controller);
        }
      } catch (error) {
        if (cancelled || controller.signal.aborted) {
          return;
        }
        clearChatRunPointer();
        if (isClassifiedApiError(error)) {
          setFailure(error.failure);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [auth, resumeOnce]);

  const reconnect = useCallback(async () => {
    if (auth === null || chat.runId === null) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setDisconnected(false);
    setReconnectExhausted(false);
    setReconnectAttempt(0);
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
    if (auth === null || chat.runId === null) {
      return;
    }
    try {
      const run = await cancelRun(auth, chat.runId);
      setChat((prev) => ({
        ...prev,
        terminal: "cancelled",
        status: run.status,
      }));
      clearChatRunPointer();
      setFailure(null);
    } catch (error) {
      if (isClassifiedApiError(error)) {
        setFailure(error.failure);
        return;
      }
      setFailure({ kind: "server", status: 500 });
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
    } catch (error) {
      if (isClassifiedApiError(error)) {
        setFeedbackStatus("Feedback could not be recorded. Try again.");
        return;
      }
      setFeedbackStatus("Feedback could not be recorded. Try again.");
    }
  }, [auth, chat.runId, feedbackComment, feedbackTag, thumbsUp]);

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

  const showChatFailureBanner = shouldShowChatFailureBanner(chat);
  const assertiveCopy = (() => {
    if (failure?.kind === "upgrade" || failure?.kind === "budget") {
      return apiFailureBanner(failure);
    }
    if (showChatFailureBanner) {
      return GENERIC_PRODUCTION_ERROR;
    }
    return "";
  })();

  if (!session.ready) {
    return (
      <div className={chatStyles.page}>
        <h2>Ask</h2>
        <p className={chatStyles.muted}>Restoring session.</p>
      </div>
    );
  }

  if (accessToken === null) {
    return (
      <div className={chatStyles.page}>
        <h2>Ask</h2>
        <StatusBanner kind="info" role="status">
          Sign in to continue.
        </StatusBanner>
        <p className={chatStyles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  if (sessionRevoked || (failure?.kind === "auth" && failure.detail === "session_revoked")) {
    return (
      <div className={chatStyles.page}>
        <h2>Ask</h2>
        <StatusBanner kind="error" role="alert">
          {SESSION_REVOKED_BANNER}
        </StatusBanner>
        <p className={chatStyles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const sendBlockReason = paidSendBlockReason(
    handshake,
    readyQuery.isPending ? undefined : readyQuery.data ?? null,
    chat,
  );
  const sendDisabled =
    sendBlockReason !== null ||
    !composerDraftIsSendable(draft);

  const citations = citationsQuery.data ?? [];
  const companyUsd = String(usageQuery.data?.cost_usd ?? "—");

  const railProps = {
    conversations: conversationsQuery.data ?? [],
    selectedId: conversationId,
    loading: conversationsQuery.isPending,
    onCreate: resetClientChat,
    onSelect: (item: ConversationResponse) => {
      if (auth === null) {
        return;
      }
      resetClientChat();
      void fetchConversation(auth, item.conversation_id).then(
        (confirmed) => {
          setConversationId(confirmed.conversation_id);
        },
        (error: unknown) => {
          if (isClassifiedApiError(error)) {
            setFailure(error.failure);
          }
        },
      );
    },
    onDelete: () => deleteMutation.mutate(),
  };

  const stage = (
    <section className={chatStyles.stage} aria-label="Answer">
      <div className={chatStyles.stageHeader}>
        {conversationId !== null ? (
        <p className={chatStyles.historyNote}>
          Continuing this session. Earlier messages are not available in this client.
        </p>
        ) : null}
        <div className={chatStyles.row}>
          {!sessionsExpanded ? (
            <Button
              type="button"
              variant="secondary"
              aria-expanded={false}
              data-action-id="ask.sessions_toggle"
              onClick={toggleSessionsExpanded}
            >
              <Icon name="panelExpand" />
              Expand sessions
            </Button>
          ) : null}
          <Button
            type="button"
            variant="ghost"
            data-action-id="ask.sources"
            onClick={() => setSourcesOpen(true)}
          >
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
      <div
        className={chatStyles.conversation}
        role="region"
        aria-label="Conversation"
        tabIndex={0}
      >
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
        {lastUserMessage === "" && chat.answerText === "" ? (
          <div className={chatStyles.emptyPrompts}>
            {PROMPT_CHIPS.map((chip) => (
              <Button
                key={chip}
                type="button"
                variant="secondary"
                onClick={() => {
                  setDraft(chip);
                }}
              >
                {chip}
              </Button>
            ))}
          </div>
        ) : null}
        {chat.terminal !== null && chat.answerText !== "" ? (
          <FeedbackPopover
            thumbsUp={thumbsUp}
            onThumbs={setThumbsUp}
            tag={feedbackTag}
            onTag={setFeedbackTag}
            comment={feedbackComment}
            onComment={setFeedbackComment}
            onSubmit={() => void sendFeedback()}
          />
        ) : null}
      </div>
      <ChatComposer
        value={draft}
        onChange={setDraft}
        onSend={() => void send()}
        onCancel={() => void cancel()}
        onReconnect={() => void reconnect()}
        sendDisabled={sendDisabled}
        running={chat.terminal === null && chat.runId !== null}
        sendBlockedReason={sendBlockReason}
        reconnectAttempt={reconnectAttempt}
        reconnectMaxAttempts={MAX_RECONNECT_ATTEMPTS}
        nextRetryMs={nextRetryMs}
        reconnectExhausted={reconnectExhausted}
      />
    </section>
  );

  return (
    <div className={chatStyles.page}>
      <header className={chatStyles.header}>
        <div>
          <h2>Ask</h2>
          <p className={chatStyles.lead}>Answers come from authorized documents and include available evidence.</p>
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

      {chat.failure !== null && showChatFailureBanner ? (
        <StatusBanner kind="error" role="alert">
          {chatRunFailureBanner(chat.failure, chat.runId)}
        </StatusBanner>
      ) : null}

      {disconnected && chat.terminal === null ? (
        <StatusBanner kind="warning" role="status">
          {reconnectExhausted
            ? `Automatic reconnect stopped after ${String(MAX_RECONNECT_ATTEMPTS)} attempts. Partial output is kept. Use Retry.`
            : reconnectAttempt > 0
              ? `Connection interrupted. Reconnecting… attempt ${String(reconnectAttempt)} of ${String(MAX_RECONNECT_ATTEMPTS)}${
                  nextRetryMs !== null ? `. Next retry in ${String(nextRetryMs)} ms.` : ""
                }`
              : "The stream disconnected. Automatic resume uses the same run. Use Reconnect if it does not recover."}
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
        <Button type="button" variant="secondary" onClick={() => setSessionsOpen(true)}>
          Sessions
        </Button>
        <Button type="button" variant="ghost" onClick={() => setSourcesOpen(true)}>
          Sources
        </Button>
      </div>

      <ChatWorkspace
        rail={
          <ConversationRail
            {...railProps}
            expanded={sessionsExpanded}
            onToggleExpanded={toggleSessionsExpanded}
            showCollapseToggle
          />
        }
        stage={stage}
        sessionsExpanded={sessionsExpanded}
      />

      {conversationsOpen ? (
        <Sheet title="Sessions" side="left" onClose={() => setSessionsOpen(false)}>
          <ConversationRail {...railProps} />
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
