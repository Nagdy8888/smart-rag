/**
 * Session-scoped Ask queries. Owns no SSE, AbortController, or reconnect timer.
 */

"use client";

import { useQuery } from "@tanstack/react-query";
import {
  fetchMeta,
  fetchUsageMe,
  listCitations,
  listConversations,
  fetchConversationMessages,
  type ApiAuth,
} from "../../../lib/api";
import { useApiAuth } from "../../../lib/auth/use-api-auth";
import { useConsoleReadiness } from "../../../lib/hooks/use-console-readiness";
import { useCurrentUser } from "../../../lib/hooks/use-current-user";
import { publicQueryKeys, sessionQueryKeys } from "../../../lib/query-keys";
import type {
  CitationResponse,
  ConversationMessage,
  ConversationResponse,
  CurrentUserResponse,
  ReadinessResponse,
  UsageResponse,
} from "../../../lib/types";

export type UseChatQueriesInput = {
  accessToken: string | null;
  conversationId: string | null;
  runId: string | null;
  terminal: boolean;
};

export type UseChatQueriesResult = {
  keys: ReturnType<typeof sessionQueryKeys>;
  auth: ApiAuth | null;
  currentUser: CurrentUserResponse | null;
  currentUserPending: boolean;
  currentUserError: unknown;
  conversations: readonly ConversationResponse[];
  conversationsPending: boolean;
  messages: readonly ConversationMessage[];
  messagesNextBeforeId: string | null;
  messagesPending: boolean;
  messagesError: boolean;
  citations: readonly CitationResponse[];
  usage: UsageResponse | null;
  meta: Awaited<ReturnType<typeof fetchMeta>> | undefined;
  metaPending: boolean;
  metaError: boolean;
  ready: ReadinessResponse | null;
  readyPending: boolean;
};

/**
 * Load handshake, identity, sessions, transcript, usage, and citations.
 *
 * Live citations load once for the current terminal run. Historical chips
 * come from `ConversationMessage.citations` and are never fetched N+1.
 *
 * @param input - Token, conversation, and run identity. No stream ownership.
 * @returns Explicit pending/error/data fields. Never a ReadableStream.
 */
export function useChatQueries(input: UseChatQueriesInput): UseChatQueriesResult {
  const { accessToken, conversationId, runId, terminal } = input;
  const auth = useApiAuth();
  const keys = sessionQueryKeys(accessToken);
  const currentUser = useCurrentUser();
  const readiness = useConsoleReadiness();

  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
    refetchInterval: (query) => (query.state.status === "error" ? 10_000 : false),
  });
  const conversationsQuery = useQuery({
    queryKey: keys.conversations,
    queryFn: () => listConversations(auth as ApiAuth),
    enabled: auth !== null,
  });
  const messagesQuery = useQuery({
    queryKey: keys.conversationMessages(conversationId),
    queryFn: () =>
      fetchConversationMessages(auth as ApiAuth, conversationId as string, {
        limit: 50,
      }),
    enabled:
      auth !== null &&
      typeof conversationId === "string" &&
      conversationId !== "" &&
      conversationId !== "undefined",
  });
  const usageQuery = useQuery({
    queryKey: keys.usage,
    queryFn: () => fetchUsageMe(auth as ApiAuth),
    enabled: auth !== null,
  });
  const citationsQuery = useQuery({
    queryKey: keys.citations(runId),
    queryFn: () => listCitations(auth as ApiAuth, runId as string),
    enabled: auth !== null && runId !== null && terminal,
  });

  return {
    keys,
    auth,
    currentUser: currentUser.currentUser,
    currentUserPending: currentUser.currentUserPending,
    currentUserError: currentUser.currentUserError,
    conversations: conversationsQuery.data ?? [],
    conversationsPending: conversationsQuery.isPending,
    messages: messagesQuery.data?.items ?? [],
    messagesNextBeforeId: messagesQuery.data?.next_before_id ?? null,
    messagesPending: messagesQuery.isLoading,
    messagesError: messagesQuery.isError,
    citations: citationsQuery.data ?? [],
    usage: usageQuery.data ?? null,
    meta: metaQuery.data,
    metaPending: metaQuery.isPending,
    metaError: metaQuery.isError,
    ready: readiness.ready,
    readyPending: readiness.readyPending,
  };
}
