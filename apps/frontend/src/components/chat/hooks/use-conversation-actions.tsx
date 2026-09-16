/**
 * Create/delete/load-older conversation actions. No live stream ownership.
 */

"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState, type RefObject } from "react";
import {
  deleteConversation,
  fetchConversation,
  fetchConversationMessages,
  generateConversationTitle,
  isClassifiedApiError,
  type ApiAuth,
  type ApiFailure,
} from "../../../lib/api";
import { sessionQueryKeys } from "../../../lib/query-keys";
import type { ConversationMessage, ConversationResponse } from "../../../lib/types";
import { ConfirmDialog } from "../../ui/confirm-dialog";

export type UseConversationActionsInput = {
  auth: ApiAuth | null;
  conversationId: string | null;
  keys: ReturnType<typeof sessionQueryKeys>;
  messagesNextBeforeId: string | null;
  onSelect: (id: string) => void;
  /** Clear the live run without dropping the selected conversation id. */
  onBeginSelect: () => void;
  onDeletedCurrent: () => void;
  onFailure: (failure: ApiFailure) => void;
  beginPrepend: () => void;
  generation: () => number;
};

export type UseConversationActionsResult = {
  olderMessages: ConversationMessage[];
  nextBeforeId: string | null;
  loadingEarlier: boolean;
  earlierError: string | null;
  deletePending: boolean;
  deleteSuccess: boolean;
  pendingDeleteId: string | null;
  deleteTriggerRef: RefObject<HTMLElement | null>;
  handleSelectConversation: (item: ConversationResponse) => void;
  handleDeleteConversation: (id: string) => void;
  confirmDelete: () => void;
  cancelDelete: () => void;
  handleLoadEarlier: () => Promise<void>;
};

/**
 * Own pagination maps and conversation mutations.
 *
 * @param input - Auth, keys, and selection callbacks.
 * @returns Older pages plus select/delete/load-earlier handlers.
 */
export function useConversationActions(
  input: UseConversationActionsInput,
): UseConversationActionsResult {
  const {
    auth,
    conversationId,
    keys,
    messagesNextBeforeId,
    onSelect,
    onBeginSelect,
    onDeletedCurrent,
    onFailure,
    beginPrepend,
    generation,
  } = input;
  const queryClient = useQueryClient();
  const [olderByConversation, setOlderByConversation] = useState<
    Record<string, ConversationMessage[]>
  >({});
  const [nextBeforeByConversation, setNextBeforeByConversation] = useState<
    Record<string, string | null>
  >({});
  const [loadingEarlier, setLoadingEarlier] = useState(false);
  const [earlierError, setEarlierError] = useState<string | null>(null);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const deleteLockRef = useRef(false);

  if (conversationId === null && (Object.keys(olderByConversation).length > 0 || earlierError !== null)) {
    setOlderByConversation({});
    setNextBeforeByConversation({});
    setEarlierError(null);
  }

  const deleteMutation = useMutation({
    mutationFn: async (id: string) => {
      if (auth === null) {
        return false;
      }
      return deleteConversation(auth, id);
    },
    onSuccess: (ok, id) => {
      if (ok) {
        setPendingDeleteId(null);
        if (conversationId === id) {
          onDeletedCurrent();
        }
        void queryClient.invalidateQueries({ queryKey: keys.conversations });
      }
    },
    onSettled: () => {
      deleteLockRef.current = false;
    },
  });

  const handleSelectConversation = useCallback(
    (item: ConversationResponse) => {
      if (auth === null) {
        return;
      }
      if (item.conversation_id !== conversationId) {
        onBeginSelect();
        onSelect(item.conversation_id);
      }
      void fetchConversation(auth, item.conversation_id).then(
        (confirmed) => {
          void generateConversationTitle(auth, confirmed.conversation_id).then(
            () => {
              void queryClient.invalidateQueries({
                queryKey: keys.conversations,
              });
            },
            () => undefined,
          );
        },
        (error: unknown) => {
          if (isClassifiedApiError(error)) {
            onFailure(error.failure);
            if (error.failure.kind === "deleted" || error.failure.kind === "auth") {
              onDeletedCurrent();
            }
          }
        },
      );
    },
    [
      auth,
      conversationId,
      keys.conversations,
      onBeginSelect,
      onDeletedCurrent,
      onFailure,
      onSelect,
      queryClient,
    ],
  );

  const olderMessages =
    conversationId === null ? [] : (olderByConversation[conversationId] ?? []);
  const nextBeforeId =
    conversationId === null
      ? null
      : Object.prototype.hasOwnProperty.call(
            nextBeforeByConversation,
            conversationId,
          )
        ? nextBeforeByConversation[conversationId]
        : messagesNextBeforeId;

  const handleLoadEarlier = useCallback(async () => {
    if (auth === null || conversationId === null || nextBeforeId === null) {
      return;
    }
    const token = generation();
    setEarlierError(null);
    beginPrepend();
    setLoadingEarlier(true);
    try {
      const page = await fetchConversationMessages(auth, conversationId, {
        limit: 50,
        before: nextBeforeId,
      });
      if (token !== generation()) {
        return;
      }
      setOlderByConversation((current) => ({
        ...current,
        [conversationId]: [
          ...page.items.slice().reverse(),
          ...(current[conversationId] ?? []),
        ],
      }));
      setNextBeforeByConversation((current) => ({
        ...current,
        [conversationId]: page.next_before_id,
      }));
    } catch {
      if (token !== generation()) {
        return;
      }
      setEarlierError("Could not load earlier messages. Try again.");
    } finally {
      if (token === generation()) {
        setLoadingEarlier(false);
      }
    }
  }, [auth, beginPrepend, conversationId, generation, nextBeforeId]);

  return {
    olderMessages,
    nextBeforeId,
    loadingEarlier,
    earlierError,
    deletePending: deleteMutation.isPending,
    deleteSuccess: deleteMutation.isSuccess,
    pendingDeleteId,
    deleteTriggerRef,
    handleSelectConversation,
    handleDeleteConversation: useCallback(
      (id: string) => {
        deleteTriggerRef.current = document.activeElement as HTMLElement | null;
        setPendingDeleteId(id);
      },
      [],
    ),
    confirmDelete: useCallback(() => {
      if (
        pendingDeleteId === null ||
        deleteLockRef.current ||
        deleteMutation.isPending
      ) {
        return;
      }
      deleteLockRef.current = true;
      deleteMutation.mutate(pendingDeleteId);
    }, [deleteMutation, pendingDeleteId]),
    cancelDelete: useCallback(() => {
      if (!deleteMutation.isPending) {
        setPendingDeleteId(null);
      }
    }, [deleteMutation.isPending]),
    handleLoadEarlier,
  };
}

/**
 * Confirm conversation deletion. Cancel and Escape send no request.
 *
 * @param props - Pending id, mutation lock, and confirm/cancel handlers.
 * @returns Dialog, or null when no delete is pending.
 */
export function ConversationDeleteDialog(props: {
  pendingDeleteId: string | null;
  pending: boolean;
  returnFocusRef: RefObject<HTMLElement | null>;
  onClose: () => void;
  onConfirm: () => void;
}) {
  if (props.pendingDeleteId === null) {
    return null;
  }
  return (
    <ConfirmDialog
      title="Delete conversation?"
      confirmLabel="Delete"
      pendingLabel="Deleting…"
      danger
      pending={props.pending}
      returnFocusRef={props.returnFocusRef}
      onClose={props.onClose}
      onConfirm={props.onConfirm}
    >
      This immediately deletes the conversation. Reads, resume, and citations
      are denied. It cannot be undone.
    </ConfirmDialog>
  );
}
