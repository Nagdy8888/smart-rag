/**
 * Paid Ask send attempt. One idempotency key per attempt, including retry.
 */

import type { QueryClient } from "@tanstack/react-query";
import {
  createConversation,
  generateConversationTitle,
  isClassifiedApiError,
  startOrResumeMessageStream,
  type ApiAuth,
  type ApiFailure,
} from "../../../lib/api";
import {
  applyAdmission,
  createChatViewState,
  type ChatViewState,
} from "../../../lib/chat-view";
import { conversationTitleFromPrompt } from "../../../lib/conversation-title";
import { composerDraftIsSendable } from "../../../lib/composer";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { paidSendBlockReason, type HandshakeDecision } from "../../../lib/handshake";
import { sessionQueryKeys } from "../../../lib/query-keys";
import { consumeSse, isAbortError } from "../../../lib/sse-consume";
import type { ReadinessResponse } from "../../../lib/types";

export type StartChatSendDeps = {
  auth: ApiAuth | null;
  conversationId: string | null;
  handshake: HandshakeDecision;
  ready: ReadinessResponse | null;
  keys: ReturnType<typeof sessionQueryKeys>;
  queryClient: QueryClient;
  onConversationId: (id: string | null) => void;
  chatRef: { current: ChatViewState };
  sequenceRef: { current: number };
  sendLockRef: { current: boolean };
  abortRef: { current: AbortController | null };
  idempotencyRef: { current: string | null };
  liveRunIdsRef: { current: Set<string> };
  /** Mark the admitted run as created in this mounted session. */
  setLiveRunCreated: (value: boolean) => void;
  autoResumeRef: {
    current: ((currentChat: ChatViewState, controller: AbortController) => Promise<void>) | null;
  };
  setChat: (chat: ChatViewState | ((prev: ChatViewState) => ChatViewState)) => void;
  setFailure: (failure: ApiFailure | null) => void;
  setSending: (value: boolean) => void;
  setLastUserMessage: (value: string) => void;
  setDisconnected: (value: boolean) => void;
  setReconnectAttempt: (value: number) => void;
  setReconnectExhausted: (value: boolean) => void;
  setNextRetryMs: (value: number | null) => void;
};

/**
 * Create the send function used by `useChatRun`.
 *
 * @param deps - Live refs and setters. The function reads latest refs on call.
 * @returns Send handler. Returns false when locked, blocked, or admit fails.
 */
export function createChatSend(deps: StartChatSendDeps): (text: string) => Promise<boolean> {
  return async (text: string): Promise<boolean> => {
    if (deps.sendLockRef.current) {
      return false;
    }
    if (deps.auth === null || !composerDraftIsSendable(text)) {
      return false;
    }
    if (paidSendBlockReason(deps.handshake, deps.ready, deps.chatRef.current) !== null) {
      return false;
    }
    deps.sendLockRef.current = true;
    deps.setSending(true);
    let admitted = false;
    let activeConversationId = deps.conversationId;
    if (activeConversationId === null) {
      try {
        const created = await createConversation(
          deps.auth,
          conversationTitleFromPrompt(text),
        );
        activeConversationId = created.conversation_id;
        if (activeConversationId === "" || activeConversationId === "undefined") {
          deps.setFailure({ kind: "server", status: 500 });
          deps.sendLockRef.current = false;
          deps.setSending(false);
          return false;
        }
        deps.onConversationId(created.conversation_id);
        void deps.queryClient.invalidateQueries({ queryKey: deps.keys.conversations });
      } catch (error) {
        deps.setFailure(
          isClassifiedApiError(error)
            ? error.failure
            : { kind: "server", status: 500 },
        );
        deps.sendLockRef.current = false;
        deps.setSending(false);
        return false;
      }
    }
    deps.setLastUserMessage(text.trim());
    deps.setDisconnected(false);
    deps.setReconnectAttempt(0);
    deps.setReconnectExhausted(false);
    deps.setNextRetryMs(null);
    deps.abortRef.current?.abort();
    const controller = new AbortController();
    deps.abortRef.current = controller;
    let current = deps.chatRef.current;
    if (current.runId === null || current.terminal !== null) {
      if (deps.idempotencyRef.current === null) {
        deps.idempotencyRef.current = newIdempotencyKey();
      }
      current = createChatViewState(deps.idempotencyRef.current);
      deps.setChat(current);
      deps.setFailure(null);
    }
    try {
      const started = await startOrResumeMessageStream(
        deps.auth,
        activeConversationId,
        text,
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
        return admitted;
      }
      if (started.failure) {
        deps.setFailure(started.failure);
        return false;
      }
      if (started.admission !== null) {
        deps.liveRunIdsRef.current.add(started.admission.run_id);
        deps.setLiveRunCreated(true);
        current = applyAdmission(current, {
          run_id: started.admission.run_id,
          reservation_id: started.admission.reservation_id,
          route_family: started.admission.route_family,
          reconnect: started.admission.reconnect,
        });
        deps.setChat(current);
        deps.setSending(false);
        admitted = true;
      }
      current = await consumeSse(
        started.response,
        current,
        controller.signal,
        deps.setChat,
        (sequence) => {
          deps.sequenceRef.current = sequence;
        },
      );
      if (controller.signal.aborted) {
        deps.setChat(current);
        return admitted;
      }
      deps.setChat(current);
      deps.sequenceRef.current = current.lastSequence;
      if (current.terminal !== null) {
        deps.idempotencyRef.current = newIdempotencyKey();
        deps.setChat((prev) => ({
          ...prev,
          idempotencyKey: deps.idempotencyRef.current as string,
        }));
        if (activeConversationId !== null) {
          const titledConversationId = activeConversationId;
          const titleAuth = deps.auth;
          void deps.queryClient
            .invalidateQueries({
              queryKey: deps.keys.conversationMessages(titledConversationId),
            })
            .then(async () => {
              if (
                (current.terminal !== "completed" &&
                  current.terminal !== "partial") ||
                titleAuth === null
              ) {
                return;
              }
              await generateConversationTitle(titleAuth, titledConversationId);
              await deps.queryClient.invalidateQueries({
                queryKey: deps.keys.conversations,
              });
            })
            .catch(() => undefined);
        }
      } else if (!controller.signal.aborted) {
        deps.setDisconnected(true);
        void deps.autoResumeRef.current?.(current, controller);
      }
      return admitted;
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) {
        return admitted;
      }
      deps.setDisconnected(true);
      void deps.autoResumeRef.current?.(deps.chatRef.current, controller);
      return admitted;
    } finally {
      deps.sendLockRef.current = false;
      deps.setSending(false);
    }
  };
}
