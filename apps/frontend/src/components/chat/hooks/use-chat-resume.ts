/**
 * Resume, automatic reconnect, and pointer recovery for one Ask run.
 */

"use client";

import { useCallback, useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import {
  fetchConversation,
  fetchRun,
  isClassifiedApiError,
  resumeEventStream,
  type ApiAuth,
  type ApiFailure,
} from "../../../lib/api";
import { classifiedOrGenericFailure } from "../../../lib/api/errors";
import { readJsonObject } from "../../../lib/api/http";
import { createChatViewState, type ChatViewState } from "../../../lib/chat-view";
import {
  clearChatRunPointer,
  isActiveRunStatus,
  readChatRunPointer,
} from "../../../lib/chat-pointer";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { consumeSse, isAbortError } from "../../../lib/sse-consume";
import {
  MAX_RECONNECT_ATTEMPTS,
  reconnectDelayMs,
  shouldStopReconnect,
  waitForReconnectDelay,
} from "../../../lib/stream-reconnect";

export type ResumeOutcome = ChatViewState | "deleted" | "unauthorized" | null;

export type UseChatResumeInput = {
  auth: ApiAuth | null;
  chatRef: MutableRefObject<ChatViewState>;
  sequenceRef: MutableRefObject<number>;
  failureRef: MutableRefObject<ApiFailure | null>;
  abortRef: MutableRefObject<AbortController | null>;
  mountedRef: MutableRefObject<boolean>;
  recoveredRef: MutableRefObject<boolean>;
  idempotencyRef: MutableRefObject<string | null>;
  autoResumeRef: MutableRefObject<
    ((currentChat: ChatViewState, controller: AbortController) => Promise<void>) | null
  >;
  setChat: Dispatch<SetStateAction<ChatViewState>>;
  setFailure: Dispatch<SetStateAction<ApiFailure | null>>;
  setDisconnected: Dispatch<SetStateAction<boolean>>;
  setReconnectAttempt: Dispatch<SetStateAction<number>>;
  setReconnectExhausted: Dispatch<SetStateAction<boolean>>;
  setNextRetryMs: Dispatch<SetStateAction<number | null>>;
  onConversationId: (id: string | null) => void;
};

/**
 * Bind resume GET, bounded auto-reconnect, and one-time pointer recovery.
 *
 * @param input - Shared run refs and state setters owned by `useChatRun`.
 * @returns `resumeOnce` used by send, reconnect, and recovery.
 */
export function useChatResume(input: UseChatResumeInput): {
  resumeOnce: (
    currentChat: ChatViewState,
    controller: AbortController,
  ) => Promise<ResumeOutcome>;
} {
  const {
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
  } = input;
  const resumeOnce = useCallback(
    async (currentChat: ChatViewState, controller: AbortController) => {
      if (auth === null || currentChat.runId === null) {
        return null;
      }
      const latest =
        chatRef.current.runId === currentChat.runId ? chatRef.current : currentChat;
      const response = await resumeEventStream(
        auth,
        latest.runId as string,
        sequenceRef.current,
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
      if (!response.ok) {
        const body = await readJsonObject(response);
        const classified = classifiedOrGenericFailure(
          response.status,
          body,
          response.headers,
        );
        setFailure(classified);
        return classified.kind === "auth" ? ("unauthorized" as const) : null;
      }
      const current = await consumeSse(
        response,
        latest,
        controller.signal,
        setChat,
        (sequence) => {
          sequenceRef.current = sequence;
        },
      );
      setChat(current);
      sequenceRef.current = current.lastSequence;
      return current;
    },
    [auth, chatRef, sequenceRef, setChat, setFailure],
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
          runDeleted: failureRef.current?.kind === "deleted",
          unmounted: !mountedRef.current,
          unauthorized: failureRef.current?.kind === "auth",
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
          if (resumed === "deleted" || resumed === "unauthorized" || resumed === null) {
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
    [
      auth,
      failureRef,
      mountedRef,
      resumeOnce,
      setDisconnected,
      setNextRetryMs,
      setReconnectAttempt,
      setReconnectExhausted,
    ],
  );

  useEffect(() => {
    autoResumeRef.current = autoResume;
  }, [autoResume, autoResumeRef]);

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
        const fetched = await fetchRun(auth, pointer.runId);
        if (cancelled || controller.signal.aborted) {
          return;
        }
        if (fetched.conversation_id !== conversation.conversation_id) {
          clearChatRunPointer();
          return;
        }
        if (!isActiveRunStatus(fetched.status)) {
          clearChatRunPointer();
          return;
        }
        onConversationId(pointer.conversationId);
        const recovered = {
          ...createChatViewState(idempotencyRef.current ?? newIdempotencyKey()),
          runId: fetched.run_id,
          lastSequence: pointer.lastSequence,
          reservationId: fetched.reservation_id,
        };
        sequenceRef.current = pointer.lastSequence;
        setChat(recovered);
        const resumed = await resumeOnce(recovered, controller);
        if (resumed === "deleted" || resumed === "unauthorized" || resumed === null || cancelled) {
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
  }, [
    abortRef,
    auth,
    autoResumeRef,
    idempotencyRef,
    onConversationId,
    recoveredRef,
    resumeOnce,
    sequenceRef,
    setChat,
    setDisconnected,
    setFailure,
  ]);

  return { resumeOnce };
}
