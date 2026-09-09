/**
 * Single owner for Ask send, resume, reconnect, and cancel.
 */

"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  cancelRun,
  isClassifiedApiError,
  type ApiAuth,
  type ApiFailure,
} from "../../../lib/api";
import type { SettledChatTurn } from "../../../lib/chat-history";
import { createChatViewState, type ChatViewState } from "../../../lib/chat-view";
import { clearChatRunPointer } from "../../../lib/chat-pointer";
import { newIdempotencyKey } from "../../../lib/idempotency";
import type { HandshakeDecision } from "../../../lib/handshake";
import { sessionCacheScope, sessionQueryKeys } from "../../../lib/query-keys";
import { isAbortError } from "../../../lib/sse-consume";
import type { ReadinessResponse, RequestedSearchScope } from "../../../lib/types";
import { createChatSend } from "./start-chat-send";
import { useChatResume } from "./use-chat-resume";
import { useChatScope } from "./use-chat-scope";
import { usePaidRunPointer } from "./use-paid-run-pointer";

export type UseChatRunInput = {
  auth: ApiAuth | null;
  conversationId: string | null;
  onConversationId: (id: string | null) => void;
  handshake: HandshakeDecision;
  ready: ReadinessResponse | null;
};

export type UseChatRunResult = {
  chat: ChatViewState;
  sending: boolean;
  disconnected: boolean;
  reconnectAttempt: number;
  reconnectExhausted: boolean;
  nextRetryMs: number | null;
  failure: ApiFailure | null;
  lastUserMessage: string;
  /** Finished live answers not yet present in GET /messages. */
  settledTurns: readonly SettledChatTurn[];
  liveRunCreated: boolean;
  searchScope: RequestedSearchScope;
  setSearchScope: (scope: RequestedSearchScope) => void;
  send(text: string): Promise<boolean>;
  reconnect(): Promise<void>;
  cancel(): Promise<void>;
  resetRun(
    reason: "new-send" | "conversation-switch" | "select-conversation" | "sign-out",
  ): void;
  setFailure: (failure: ApiFailure | null) => void;
};

/**
 * Drive one paid Ask run. Parses no SSE bytes; `consumeSse` remains the engine.
 *
 * @param input - Auth, conversation id, and handshake/readiness gates.
 * @returns Chat view plus send/resume/cancel controls.
 */
export function useChatRun(input: UseChatRunInput): UseChatRunResult {
  const { auth, conversationId, onConversationId, handshake, ready } = input;
  const queryClient = useQueryClient();
  const [chat, setChat] = useState<ChatViewState>(() =>
    createChatViewState(newIdempotencyKey()),
  );
  const [sending, setSending] = useState(false);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [lastUserMessage, setLastUserMessage] = useState("");
  const [settledTurns, setSettledTurns] = useState<SettledChatTurn[]>([]);
  const lastUserMessageRef = useRef("");
  const [disconnected, setDisconnected] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState(0);
  const [reconnectExhausted, setReconnectExhausted] = useState(false);
  const [nextRetryMs, setNextRetryMs] = useState<number | null>(null);
  const [liveRunCreated, setLiveRunCreated] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const sendLockRef = useRef(false);
  const idempotencyRef = useRef<string | null>(chat.idempotencyKey);
  const recoveredRef = useRef(false);
  const liveRunIdsRef = useRef(new Set<string>());
  const scopeBindingRef = useRef<{
    idempotencyKey: string;
    requestedSearchScope: RequestedSearchScope;
  } | null>(null);
  const {
    scope: searchScope,
    setScope: setSearchScope,
    bindCreatedConversation,
    activateConversation,
    restoreConversationScope,
    resetForNewChat,
  } = useChatScope(conversationId);
  const chatRef = useRef(chat);
  const sequenceRef = useRef(chat.lastSequence);
  const failureRef = useRef(failure);
  const autoResumeRef = useRef<
    ((currentChat: ChatViewState, controller: AbortController) => Promise<void>) | null
  >(null);
  const sendDepsRef = useRef<Parameters<typeof createChatSend>[0] | null>(null);
  useLayoutEffect(() => {
    chatRef.current = chat;
    sequenceRef.current = chat.lastSequence;
    failureRef.current = failure;
    lastUserMessageRef.current = lastUserMessage;
  }, [chat, failure, lastUserMessage]);
  const settleCompletedTurn = useCallback((turn: SettledChatTurn) => {
    setSettledTurns((previous) => [...previous, turn]);
  }, []);
  const keys = sessionQueryKeys(auth?.accessToken ?? null);

  usePaidRunPointer({
    conversationId,
    runId: chat.runId,
    lastSequence: chat.lastSequence,
    terminal: chat.terminal,
  });

  const resetRun = useCallback(
    (
      reason:
        | "new-send"
        | "conversation-switch"
        | "select-conversation"
        | "sign-out",
    ) => {
      abortRef.current?.abort();
      abortRef.current = null;
      clearChatRunPointer();
      sendLockRef.current = false;
      idempotencyRef.current = newIdempotencyKey();
      scopeBindingRef.current = null;
      liveRunIdsRef.current.clear();
      setLiveRunCreated(false);
      setSettledTurns([]);
      if (reason !== "new-send" && reason !== "select-conversation") {
        onConversationId(null);
        setLastUserMessage("");
        resetForNewChat();
      }
      if (reason === "select-conversation") {
        setLastUserMessage("");
      }
      setSending(false);
      setChat(createChatViewState(idempotencyRef.current));
      setFailure(null);
      setDisconnected(false);
      setReconnectAttempt(0);
      setReconnectExhausted(false);
      setNextRetryMs(null);
    },
    [onConversationId, resetForNewChat],
  );

  useEffect(() => {
    if (conversationId === null) {
      return;
    }
    activateConversation(conversationId);
  }, [activateConversation, conversationId]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const previousScopeRef = useRef(sessionCacheScope(auth?.accessToken ?? null));
  useEffect(() => {
    const next = sessionCacheScope(auth?.accessToken ?? null);
    const previous = previousScopeRef.current;
    previousScopeRef.current = next;
    if (previous !== null && previous !== next) {
      recoveredRef.current = false;
      resetRun("sign-out");
      void queryClient.removeQueries({
        predicate: (query) => query.queryKey.includes(previous),
      });
    }
  }, [auth?.accessToken, queryClient, resetRun]);

  const resumeInput = useMemo(
    () => ({
      auth,
      chatRef,
      sequenceRef,
      failureRef,
      abortRef,
      mountedRef,
      recoveredRef,
      idempotencyRef,
      autoResumeRef,
      setChat,
      setFailure,
      setDisconnected,
      setReconnectAttempt,
      setReconnectExhausted,
      setNextRetryMs,
      onConversationId,
      restoreConversationScope,
    }),
    [auth, onConversationId, restoreConversationScope],
  );
  const { resumeOnce } = useChatResume(resumeInput);

  useLayoutEffect(() => {
    sendDepsRef.current = {
      auth,
      conversationId,
      handshake,
      ready,
      keys,
      queryClient,
      onConversationId,
      chatRef,
      sequenceRef,
      sendLockRef,
      abortRef,
      idempotencyRef,
      liveRunIdsRef,
      lastUserMessageRef,
      autoResumeRef,
      setLiveRunCreated,
      settleCompletedTurn,
      setChat,
      setFailure,
      setSending,
      setLastUserMessage,
      setDisconnected,
      setReconnectAttempt,
      setReconnectExhausted,
      setNextRetryMs,
      requestedSearchScope: searchScope,
      bindCreatedConversation,
      bindSearchScope: (key, current) => {
        if (scopeBindingRef.current?.idempotencyKey === key) {
          return scopeBindingRef.current.requestedSearchScope;
        }
        scopeBindingRef.current = {
          idempotencyKey: key,
          requestedSearchScope: current,
        };
        return current;
      },
      clearSearchScopeBinding: () => {
        scopeBindingRef.current = null;
      },
    };
  }, [
    auth,
    bindCreatedConversation,
    searchScope,
    conversationId,
    handshake,
    keys,
    onConversationId,
    queryClient,
    ready,
    settleCompletedTurn,
  ]);
  const send = useCallback(async (text: string) => {
    const deps = sendDepsRef.current;
    if (deps === null) {
      return false;
    }
    return createChatSend(deps)(text);
  }, []);

  const reconnect = useCallback(async () => {
    const currentChat = chatRef.current;
    if (auth === null || currentChat.runId === null) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setDisconnected(false);
    setReconnectExhausted(false);
    setReconnectAttempt(0);
    try {
      const resumed = await resumeOnce(currentChat, controller);
      if (resumed === "deleted" || resumed === "unauthorized" || resumed === null) {
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
  }, [auth, resumeOnce]);

  const cancel = useCallback(async () => {
    abortRef.current?.abort();
    const runId = chatRef.current.runId;
    if (auth === null || runId === null) {
      return;
    }
    try {
      const run = await cancelRun(auth, runId);
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
  }, [auth]);

  return {
    chat,
    sending,
    disconnected,
    reconnectAttempt,
    reconnectExhausted,
    nextRetryMs,
    failure,
    lastUserMessage,
    settledTurns,
    liveRunCreated,
    searchScope,
    setSearchScope,
    send,
    reconnect,
    cancel,
    resetRun,
    setFailure,
  };
}
