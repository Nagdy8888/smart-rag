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
  snapshotSettledTurn,
  type SettledChatTurn,
} from "../../../lib/chat-history";
import {
  addChatTokens,
  applyAdmission,
  startNextChatRun,
  type ChatViewState,
} from "../../../lib/chat-view";
import { conversationTitleFromPrompt } from "../../../lib/conversation-title";
import { composerDraftIsSendable } from "../../../lib/composer";
import { newIdempotencyKey } from "../../../lib/idempotency";
import { paidSendBlockReason, type HandshakeDecision } from "../../../lib/handshake";
import { sessionQueryKeys } from "../../../lib/query-keys";
import { consumeSse, isAbortError } from "../../../lib/sse-consume";
import type { ReadinessResponse, RequestedSearchScope } from "../../../lib/types";

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
  /** Previous live question; snapshotted before the next send overwrites it. */
  lastUserMessageRef: { current: string };
  /** Fold a finished live answer into the transcript overlay. */
  settleCompletedTurn: (turn: SettledChatTurn) => void;
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
  requestedSearchScope: RequestedSearchScope;
  bindCreatedConversation: (conversationId: string) => void;
  bindSearchScope: (
    idempotencyKey: string,
    current: RequestedSearchScope,
  ) => RequestedSearchScope;
  clearSearchScopeBinding: () => void;
};

/**
 * Consume an admitted SSE body, settle title, and reconnect. Does not
 * block composer `onSubmit` settlement.
 *
 * @param deps - Live send deps.
 * @param response - Open `GET /runs/{id}/events` body.
 * @param current - View after admission or resume.
 * @param controller - Abort from Stop, New chat, or a replacement send.
 * @param conversationId - Conversation to title after a terminal.
 */
async function finishAdmittedStream(
  deps: StartChatSendDeps,
  response: Response,
  current: ChatViewState,
  controller: AbortController,
  conversationId: string,
): Promise<void> {
  try {
    const next = await consumeSse(
      response,
      current,
      controller.signal,
      deps.setChat,
      (sequence) => {
        deps.sequenceRef.current = sequence;
      },
    );
    if (controller.signal.aborted) {
      deps.setChat(next);
      return;
    }
    deps.setChat(next);
    deps.sequenceRef.current = next.lastSequence;
    if (next.terminal !== null) {
      deps.clearSearchScopeBinding();
      deps.idempotencyRef.current = newIdempotencyKey();
      deps.setChat((prev) => ({
        ...prev,
        idempotencyKey: deps.idempotencyRef.current as string,
      }));
      const titleAuth = deps.auth;
      void deps.queryClient
        .invalidateQueries({
          queryKey: deps.keys.conversationMessages(conversationId),
        })
        .then(async () => {
          if (
            (next.terminal !== "completed" && next.terminal !== "partial") ||
            titleAuth === null
          ) {
            return;
          }
          const titled = await generateConversationTitle(titleAuth, conversationId);
          deps.setChat((prev) =>
            addChatTokens(
              prev,
              titled.prompt_tokens ?? 0,
              titled.completion_tokens ?? 0,
            ),
          );
          await deps.queryClient.invalidateQueries({
            queryKey: deps.keys.conversations,
          });
        })
        .catch(() => undefined);
    } else if (!controller.signal.aborted) {
      deps.setDisconnected(true);
      void deps.autoResumeRef.current?.(next, controller);
    }
  } catch (error) {
    if (controller.signal.aborted || isAbortError(error)) {
      return;
    }
    deps.setDisconnected(true);
    void deps.autoResumeRef.current?.(deps.chatRef.current, controller);
  }
}

/**
 * Create the send function used by `useChatRun`.
 *
 * @param deps - Live refs and setters. The function reads latest refs on call.
 * @returns Send handler. Returns false when locked, blocked, or admit fails.
 *   Returns true as soon as the stream is handed off so the composer does
 *   not wait for the verified answer.
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
    const capturedScope = deps.requestedSearchScope;
    const settled = snapshotSettledTurn(
      deps.lastUserMessageRef.current,
      deps.chatRef.current,
      new Date().toISOString(),
    );
    if (settled !== null) {
      deps.settleCompletedTurn(settled);
    }
    deps.setLastUserMessage(text.trim());
    let streamHandedOff = false;
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
          deps.setLastUserMessage("");
          deps.sendLockRef.current = false;
          deps.setSending(false);
          return false;
        }
        deps.bindCreatedConversation(created.conversation_id);
        deps.onConversationId(created.conversation_id);
        void deps.queryClient.invalidateQueries({ queryKey: deps.keys.conversations });
      } catch (error) {
        deps.setFailure(
          isClassifiedApiError(error)
            ? error.failure
            : { kind: "server", status: 500 },
        );
        deps.setLastUserMessage("");
        deps.sendLockRef.current = false;
        deps.setSending(false);
        return false;
      }
    }
    if (activeConversationId === null) {
      deps.setLastUserMessage("");
      deps.sendLockRef.current = false;
      deps.setSending(false);
      return false;
    }
    deps.setDisconnected(false);
    deps.setReconnectAttempt(0);
    deps.setReconnectExhausted(false);
    deps.setNextRetryMs(null);
    deps.abortRef.current?.abort();
    const controller = new AbortController();
    deps.abortRef.current = controller;
    let current = deps.chatRef.current;
    if (current.runId === null || current.terminal !== null) {
      const nextKey = deps.idempotencyRef.current ?? newIdempotencyKey();
      deps.idempotencyRef.current = nextKey;
      current = startNextChatRun(current, nextKey);
      deps.setChat(current);
      deps.setFailure(null);
    }
    const searchScope = deps.bindSearchScope(current.idempotencyKey, capturedScope);
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
        searchScope,
        fetch,
        controller.signal,
      );
      if (controller.signal.aborted) {
        deps.setLastUserMessage("");
        return false;
      }
      if (started.failure) {
        deps.setFailure(started.failure);
        deps.setLastUserMessage("");
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
          requested_search_scope: started.admission.requested_search_scope,
        });
        deps.setChat(current);
        deps.setSending(false);
      }
      streamHandedOff = true;
      void finishAdmittedStream(
        deps,
        started.response,
        current,
        controller,
        activeConversationId,
      ).finally(() => {
        deps.sendLockRef.current = false;
        deps.setSending(false);
      });
      return true;
    } catch (error) {
      if (controller.signal.aborted || isAbortError(error)) {
        deps.setLastUserMessage("");
        return false;
      }
      deps.setDisconnected(true);
      void deps.autoResumeRef.current?.(deps.chatRef.current, controller);
      deps.setLastUserMessage("");
      return false;
    } finally {
      if (!streamHandedOff) {
        deps.sendLockRef.current = false;
        deps.setSending(false);
      }
    }
  };
}
