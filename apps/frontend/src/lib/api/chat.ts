/**
 * Conversation and run HTTP helpers.
 */

import {
  clampCitationCount,
  parseTranscriptSourceKind,
} from "../chat-restore";
import { parseKnowledgeResult } from "../knowledge-result";
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
import { parseConversationResponse, parseRunResponse } from "./parsers";

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
  return parsed.flatMap((item) => {
    if (item === null || typeof item !== "object") {
      return [];
    }
    return [parseConversationResponse(item as Record<string, unknown>)];
  });
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
  return parseConversationResponse(body);
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
  return parseConversationResponse(body);
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
    ? body.items.flatMap((item) => {
        const parsed = parseConversationMessage(item);
        return parsed === null ? [] : [parsed];
      })
    : [];
  const next =
    body.next_before_id === null || body.next_before_id === undefined
      ? null
      : String(body.next_before_id);
  return { items, next_before_id: next };
}

/**
 * Parse one transcript row.
 *
 * List payloads never include excerpts. `citations` stays empty so the
 * client cannot N+1 detail fetches from the transcript page.
 *
 * @param item - Raw message JSON.
 * @returns Typed message, or null when identity/role is invalid.
 */
function parseConversationMessage(item: unknown): ConversationMessage | null {
  if (item === null || typeof item !== "object" || Array.isArray(item)) {
    return null;
  }
  const row = item as Record<string, unknown>;
  const role = row.role;
  if (role !== "user" && role !== "assistant") {
    return null;
  }
  const messageId = row.message_id;
  if (typeof messageId !== "string" || messageId.trim() === "") {
    return null;
  }
  return {
    message_id: messageId,
    role,
    content: typeof row.content === "string" ? row.content : "",
    created_at: typeof row.created_at === "string" ? row.created_at : "",
    run_id:
      typeof row.run_id === "string" && row.run_id.trim() !== ""
        ? row.run_id
        : null,
    citation_count: clampCitationCount(row.citation_count),
    source_kind: parseTranscriptSourceKind(row.source_kind),
    knowledge_result: parseKnowledgeResult(row.knowledge_result),
    citations: [],
  };
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
 * @returns Conversation with the persisted title and this call's tokens.
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
  return parseConversationResponse(body);
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
