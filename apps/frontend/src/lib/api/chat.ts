/**
 * Conversation and run HTTP helpers.
 */

import type {
  ConversationMessage,
  ConversationMessagesResponse,
  ConversationResponse,
  RunResponse,
} from "../types";
import { throwIfNotOk } from "./errors";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders, resumeHeaders } from "./headers";
import { apiUrl, readJsonObject } from "./http";
import { parseRunResponse } from "./parsers";

/**
 * List conversations the caller may read.
 *
 * @param auth - Access token.
 * @param fetchImpl - Injected fetch.
 * @returns Conversation rows.
 */
export async function listConversations(
  auth: ApiAuth,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationResponse[]> {
  const response = await fetchImpl(apiUrl("/conversations"), {
    headers: resumeHeaders(auth),
  });
  const parsed: unknown = await response.json();
  if (!Array.isArray(parsed)) {
    return [];
  }
  return parsed as ConversationResponse[];
}

/**
 * Create a conversation.
 *
 * @param auth - Access token.
 * @param title - Optional title.
 * @param fetchImpl - Injected fetch.
 * @returns Created conversation.
 * @throws ClassifiedApiError on non-OK responses.
 */
export async function createConversation(
  auth: ApiAuth,
  title: string | null,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationResponse> {
  const response = await fetchImpl(apiUrl("/conversations"), {
    method: "POST",
    headers: paidMutationHeaders(auth),
    body: JSON.stringify(title ? { title } : {}),
  });
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  return {
    conversation_id: String(body.conversation_id ?? ""),
    creator_user_id: String(body.creator_user_id ?? ""),
    title:
      body.title === null || body.title === undefined
        ? null
        : String(body.title),
    created_at:
      body.created_at === null || body.created_at === undefined
        ? null
        : String(body.created_at),
  };
}

/**
 * Fetch one owned conversation. Foreign or tombstoned ids are 404.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Conversation row.
 * @throws ClassifiedApiError on non-OK responses.
 */
export async function fetchConversation(
  auth: ApiAuth,
  conversationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationResponse> {
  const response = await fetchImpl(apiUrl(`/conversations/${conversationId}`), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  return body as unknown as ConversationResponse;
}

/**
 * Load one page of persisted user/assistant messages, newest first.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param options - Page size (1–100) and optional keyset cursor.
 * @param fetchImpl - Injected fetch.
 * @returns Escaped transcript items and the next older cursor.
 * @throws ClassifiedApiError on non-OK responses.
 */
export async function fetchConversationMessages(
  auth: ApiAuth,
  conversationId: string,
  options: { limit?: number; before?: string | null } = {},
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationMessagesResponse> {
  const params = new URLSearchParams();
  params.set("limit", String(options.limit ?? 50));
  if (options.before) {
    params.set("before", options.before);
  }
  const response = await fetchImpl(
    apiUrl(`/conversations/${conversationId}/messages?${params.toString()}`),
    { headers: resumeHeaders(auth) },
  );
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  const items = Array.isArray(body.items)
    ? (body.items as ConversationMessage[])
    : [];
  const next =
    body.next_before_id === null || body.next_before_id === undefined
      ? null
      : String(body.next_before_id);
  return { items, next_before_id: next };
}

/**
 * Fetch one owned run. Foreign runs are 404.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Run identifiers. No answer or citation text.
 * @throws ClassifiedApiError on non-OK responses.
 */
export async function fetchRun(
  auth: ApiAuth,
  runId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<RunResponse> {
  const response = await fetchImpl(apiUrl(`/runs/${runId}`), {
    headers: resumeHeaders(auth),
  });
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  return parseRunResponse(body);
}

/**
 * Ask the API to replace a first-prompt fallback with an LLM session title.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param fetchImpl - Injected fetch.
 * @returns Conversation with the persisted title.
 * @throws ClassifiedApiError on non-OK responses.
 */
export async function generateConversationTitle(
  auth: ApiAuth,
  conversationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<ConversationResponse> {
  const response = await fetchImpl(
    apiUrl(`/conversations/${conversationId}/title`),
    {
      method: "POST",
      headers: paidMutationHeaders(auth),
    },
  );
  const body = await readJsonObject(response);
  throwIfNotOk(response, body);
  return {
    conversation_id: String(body.conversation_id ?? ""),
    creator_user_id: String(body.creator_user_id ?? ""),
    title:
      body.title === null || body.title === undefined
        ? null
        : String(body.title),
    created_at:
      body.created_at === null || body.created_at === undefined
        ? null
        : String(body.created_at),
  };
}

/**
 * Tombstone and purge one conversation.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param fetchImpl - Injected fetch.
 * @returns True on 204.
 */
export async function deleteConversation(
  auth: ApiAuth,
  conversationId: string,
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> {
  const response = await fetchImpl(apiUrl(`/conversations/${conversationId}`), {
    method: "DELETE",
    headers: resumeHeaders(auth),
  });
  return response.status === 204;
}
