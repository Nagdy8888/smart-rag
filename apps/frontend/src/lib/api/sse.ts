/**
 * Admit and resume EventSource bodies. Does not parse SSE frames.
 */

import type { SubmitMessageResponse } from "../types";
import { classifiedOrGenericFailure, type ApiFailure } from "./errors";
import type { ApiAuth } from "./headers";
import { paidMutationHeaders, resumeHeaders, submitMessageBody } from "./headers";
import { apiUrl, readJsonObject } from "./http";

export type StreamStart = {
  response: Response;
  admission: SubmitMessageResponse | null;
  failure: ApiFailure | null;
  /** True when the client skipped POST and used GET resume for an existing run. */
  resumed: boolean;
};

/** Minimal run snapshot used to prefer resume over a second paid POST. */
export type PaidRunPointer = {
  runId: string | null;
  terminal: string | null;
  lastSequence: number;
  idempotencyKey: string;
};

/**
 * Return whether the client must resume GET instead of posting again.
 *
 * @param state - Current chat run.
 * @returns True when `runId` is set and the run is not terminal.
 */
export function shouldResumeExistingRun(state: PaidRunPointer): boolean {
  return state.runId !== null && state.terminal === null;
}

/**
 * POST a chat message with JSON Accept so the 202 body includes `run_id`.
 * Handshake runs before admit. The EventSource body is `GET /runs/{id}/events`.
 *
 * Reconnect uses the same run and never starts a second paid reservation.
 * Cancel and a new send pass `signal` so admit POST and resume GET abort.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param message - Untrusted user text.
 * @param idempotencyKey - Stable UUID reused on retry.
 * @param fetchImpl - Injected fetch.
 * @param signal - Abort from Cancel or a replacement send.
 * @returns Streaming GET response plus admission JSON, or a typed failure.
 */
export async function startMessageStream(
  auth: ApiAuth,
  conversationId: string,
  message: string,
  idempotencyKey: string,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<StreamStart> {
  const admitHeaders = {
    ...paidMutationHeaders(auth, idempotencyKey),
    Accept: "application/json",
  };
  const admitResponse = await fetchImpl(
    apiUrl(`/conversations/${conversationId}/messages`),
    {
      method: "POST",
      headers: admitHeaders,
      body: JSON.stringify(submitMessageBody(message, idempotencyKey)),
      signal,
    },
  );
  if (!admitResponse.ok) {
    const body = await readJsonObject(admitResponse);
    return {
      response: admitResponse,
      admission: null,
      failure: classifiedOrGenericFailure(
        admitResponse.status,
        body,
        admitResponse.headers,
      ),
      resumed: false,
    };
  }
  const admission = (await admitResponse.json()) as SubmitMessageResponse;
  const stream = await resumeEventStream(
    auth,
    admission.run_id,
    0,
    fetchImpl,
    signal,
  );
  if (!stream.ok) {
    const body = await readJsonObject(stream);
    return {
      response: stream,
      admission,
      failure: classifiedOrGenericFailure(stream.status, body, stream.headers),
      resumed: false,
    };
  }
  return { response: stream, admission, failure: null, resumed: false };
}

/**
 * Resume an in-flight run when `runId` is already known; otherwise admit.
 *
 * Reusing the stored run never sends a second paid POST from this client.
 * If this helper does POST (no `runId` yet), the server still reuses the
 * idempotency key.
 *
 * @param auth - Access token.
 * @param conversationId - Conversation UUID.
 * @param message - Untrusted user text. Ignored on resume.
 * @param state - Current run pointer.
 * @param fetchImpl - Injected fetch.
 * @param signal - Abort from Cancel or a replacement send.
 * @returns Stream start. `resumed` is true when POST was skipped.
 */
export async function startOrResumeMessageStream(
  auth: ApiAuth,
  conversationId: string,
  message: string,
  state: PaidRunPointer,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<StreamStart> {
  if (shouldResumeExistingRun(state) && state.runId !== null) {
    const stream = await resumeEventStream(
      auth,
      state.runId,
      state.lastSequence,
      fetchImpl,
      signal,
    );
    if (!stream.ok) {
      const body = await readJsonObject(stream);
      return {
        response: stream,
        admission: null,
        failure: classifiedOrGenericFailure(stream.status, body, stream.headers),
        resumed: true,
      };
    }
    return {
      response: stream,
      admission: null,
      failure: null,
      resumed: true,
    };
  }
  return startMessageStream(
    auth,
    conversationId,
    message,
    state.idempotencyKey,
    fetchImpl,
    signal,
  );
}

/**
 * Resume an admitted run. Does not send `X-Client-Version`.
 *
 * @param auth - Access token.
 * @param runId - Run UUID.
 * @param after - Last applied sequence.
 * @param fetchImpl - Injected fetch.
 * @param signal - Abort from Cancel or a replacement send.
 * @returns SSE response.
 */
export async function resumeEventStream(
  auth: ApiAuth,
  runId: string,
  after: number,
  fetchImpl: typeof fetch = fetch,
  signal?: AbortSignal,
): Promise<Response> {
  const url = apiUrl(`/runs/${runId}/events?after=${encodeURIComponent(String(after))}`);
  return fetchImpl(url, {
    headers: {
      ...resumeHeaders(auth),
      Accept: "text/event-stream",
    },
    signal,
  });
}
