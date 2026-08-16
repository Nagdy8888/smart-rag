/**
 * Thin authenticated developer console. Not Stitch or production UI.
 *
 * Server authorization is authoritative. Hidden controls are convenience only.
 */

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import {
  cancelRun,
    createConversation,
    deleteConversation,
    fetchMe,
    fetchMeta,
    fetchUsageMe,
    fetchVersionStatus,
    listCitations,
    listConversations,
    listDocuments,
    reserveUpload,
    startMessageStream,
  submitFeedback,
  resumeEventStream,
  type ApiAuth,
  type ApiFailure,
} from "../lib/api";
import { createBrowserSupabase } from "../lib/auth/browser";
import {
  applyAdmission,
  applySseFrame,
  createChatViewState,
  type ChatViewState,
} from "../lib/chat-view";
import { publicSupabaseConfig } from "../lib/env";
import {
  formatBm25Summary,
  formatGraphHandoffSummary,
} from "../lib/ingestion-status";
import { graphNotReadyCopy, limitationCopy } from "../lib/limitations";
import { displayText, formatProvenance, isSafeHttpUrl } from "../lib/safe-text";
import { parseSseBuffer } from "../lib/sse";
import { FEEDBACK_TAGS, type FeedbackTag } from "../lib/types";
import styles from "./developer-app.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

async function consumeSse(
  response: Response,
  initial: ChatViewState,
  signal: AbortSignal,
  onState: (state: ChatViewState) => void,
): Promise<ChatViewState> {
  const reader = response.body?.getReader();
  if (!reader) {
    return initial;
  }
  const decoder = new TextDecoder();
  let buffer = "";
  let current = initial;
  try {
    while (!signal.aborted) {
      const chunk = await reader.read();
      if (chunk.done) {
        break;
      }
      buffer += decoder.decode(chunk.value, { stream: true });
      const parsed = parseSseBuffer(buffer);
      buffer = parsed.rest;
      for (const frame of parsed.frames) {
        current = applySseFrame(current, frame);
        onState(current);
        if (current.terminal !== null) {
          return current;
        }
      }
    }
  } finally {
    await reader.cancel().catch(() => undefined);
  }
  return current;
}

/**
 * Render the thin developer UI for sign-in, upload status, chat, citations,
 * feedback, and conversation deletion.
 *
 * @returns Developer console.
 */
export function DeveloperApp() {
  const queryClient = useQueryClient();
  const supabase = useMemo(() => createBrowserSupabase(), []);
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [authError, setAuthError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [chat, setChat] = useState<ChatViewState>(() =>
    createChatViewState("00000000-0000-4000-8000-000000000001"),
  );
  const idempotencyRef = useRef<string | null>(null);
  const [failure, setFailure] = useState<ApiFailure | null>(null);
  const [feedbackTag, setFeedbackTag] = useState<FeedbackTag>(FEEDBACK_TAGS[0]);
  const [feedbackComment, setFeedbackComment] = useState("");
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const auth = useMemo<ApiAuth | null>(
    () => (accessToken ? { accessToken } : null),
    [accessToken],
  );

  const metaQuery = useQuery({
    queryKey: ["meta"],
    queryFn: () => fetchMeta(),
  });

  const meQuery = useQuery({
    queryKey: ["me", accessToken],
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const conversationsQuery = useQuery({
    queryKey: ["conversations", accessToken],
    queryFn: () => listConversations(auth as ApiAuth),
    enabled: auth !== null,
  });

  const documentsQuery = useQuery({
    queryKey: ["documents", accessToken],
    queryFn: () => listDocuments(auth as ApiAuth),
    enabled: auth !== null,
  });

  const versionStatusQuery = useQuery({
    queryKey: ["version-status", accessToken, selectedVersionId],
    queryFn: () => fetchVersionStatus(auth as ApiAuth, selectedVersionId as string),
    enabled: auth !== null && selectedVersionId !== null,
  });

  const usageQuery = useQuery({
    queryKey: ["usage", accessToken],
    queryFn: () => fetchUsageMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const citationsQuery = useQuery({
    queryKey: ["citations", accessToken, chat.runId],
    queryFn: () => listCitations(auth as ApiAuth, chat.runId as string),
    enabled: auth !== null && chat.runId !== null && chat.terminal !== null,
  });

  const createMutation = useMutation({
    mutationFn: () => createConversation(auth as ApiAuth, "Developer thread"),
    onSuccess: (created) => {
      setConversationId(created.conversation_id);
      void queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  const uploadMutation = useMutation({
    mutationFn: () =>
      reserveUpload(auth as ApiAuth, 1024, newIdempotencyKey()),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => {
      if (auth === null || conversationId === null) {
        return false;
      }
      return deleteConversation(auth, conversationId);
    },
    onSuccess: (ok) => {
      if (ok) {
        setConversationId(null);
        idempotencyRef.current = newIdempotencyKey();
        setChat(createChatViewState(idempotencyRef.current));
        void queryClient.invalidateQueries({ queryKey: ["conversations"] });
      }
    },
  });

  const signIn = useCallback(async () => {
    setAuthError(null);
    if (supabase === null) {
      setAuthError("supabase_unconfigured");
      return;
    }
    const result = await supabase.auth.signInWithPassword({ email, password });
    if (result.error) {
      setAuthError(result.error.message);
      return;
    }
    const token = result.data.session?.access_token;
    if (!token) {
      setAuthError("session_missing");
      return;
    }
    setAccessToken(token);
  }, [email, password, supabase]);

  const signOut = useCallback(async () => {
    await supabase?.auth.signOut();
    setAccessToken(null);
  }, [supabase]);

  const send = useCallback(async () => {
    if (auth === null || conversationId === null || draft.trim() === "") {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    if (idempotencyRef.current === null) {
      idempotencyRef.current = newIdempotencyKey();
    }
    const next = createChatViewState(idempotencyRef.current);
    setChat(next);
    setFailure(null);
    const started = await startMessageStream(
      auth,
      conversationId,
      draft,
      next.idempotencyKey,
    );
    if (started.failure) {
      setFailure(started.failure);
      return;
    }
    let current = next;
    if (started.admission !== null) {
      current = applyAdmission(current, {
        run_id: started.admission.run_id,
        reservation_id: started.admission.reservation_id,
        route_family: started.admission.route_family,
        reconnect: started.admission.reconnect,
      });
      setChat(current);
    }
    current = await consumeSse(started.response, current, controller.signal, setChat);
    setChat(current);
    if (current.terminal !== null) {
      idempotencyRef.current = newIdempotencyKey();
      setChat((prev) => ({ ...prev, idempotencyKey: idempotencyRef.current as string }));
    }
  }, [auth, conversationId, draft]);

  const reconnect = useCallback(async () => {
    if (auth === null || chat.runId === null) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const response = await resumeEventStream(auth, chat.runId, chat.lastSequence);
    if (response.status === 404) {
      setFailure({ kind: "deleted" });
      return;
    }
    const current = await consumeSse(response, chat, controller.signal, setChat);
    setChat(current);
  }, [auth, chat]);

  const cancel = useCallback(async () => {
    abortRef.current?.abort();
    if (auth !== null && chat.runId !== null) {
      await cancelRun(auth, chat.runId);
    }
  }, [auth, chat.runId]);

  const sendFeedback = useCallback(async () => {
    if (auth === null || chat.runId === null) {
      return;
    }
    await submitFeedback(
      auth,
      chat.runId,
      true,
      feedbackTag,
      feedbackComment || null,
    );
  }, [auth, chat.runId, feedbackComment, feedbackTag]);

  if (accessToken === null) {
    return (
      <div className={styles.shell}>
        <h1>Smart RAG developer console</h1>
        <p className={styles.muted}>
          Thin Phase 6 UI. Browser-direct Supabase Auth, then Bearer FastAPI.
          Role hiding is not authorization. After sign-in: Auto Composite chat,
          upload reservation (local signed_url is null until Phase 10), BM25
          version status, citations, and conversation delete.
        </p>
        {publicSupabaseConfig() === null ? (
          <p className={styles.banner} data-kind="error" role="alert">
            Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.
          </p>
        ) : null}
        {authError ? (
          <p className={styles.banner} data-kind="error" role="alert">
            {displayText(authError)}
          </p>
        ) : null}
        <form
          className={styles.panel}
          onSubmit={(event) => {
            event.preventDefault();
            void signIn();
          }}
        >
          <label>
            Email
            <input
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          <button type="submit">Sign in</button>
        </form>
      </div>
    );
  }

  return (
    <div className={styles.shell}>
      <header className={styles.row}>
        <h1>Smart RAG developer console</h1>
        <p className={styles.muted}>
          Signed in as {displayText(meQuery.data?.role ?? "unknown")}{" "}
          {displayText(meQuery.data?.user_id ?? "")}. Server role is
          authoritative.
        </p>
        <button type="button" onClick={() => void signOut()}>
          Sign out
        </button>
      </header>

      {failure?.kind === "upgrade" ? (
        <p className={styles.banner} role="alert">
          Client upgrade required. Minimum {failure.minClientVersion}, SSE schema{" "}
          {failure.sseSchemaVersion}.
        </p>
      ) : null}
      {failure?.kind === "auth" ? (
        <p className={styles.banner} data-kind="error" role="alert">
          Session rejected ({failure.detail}). Sign in again. UI state is not
          authorization.
        </p>
      ) : null}
      {failure?.kind === "deleted" || deleteMutation.isSuccess ? (
        <p className={styles.banner} role="status">
          Conversation deleted. Reads, resume, and citations are denied. No
          source text is shown.
        </p>
      ) : null}

      <div className={styles.grid}>
        <aside className={styles.panel}>
          <h2>Conversations</h2>
          <div className={styles.row}>
            <button type="button" onClick={() => createMutation.mutate()}>
              New conversation
            </button>
            <button
              type="button"
              onClick={() => deleteMutation.mutate()}
              disabled={conversationId === null}
            >
              Delete conversation
            </button>
          </div>
          <ul className={styles.list}>
            {(conversationsQuery.data ?? []).map((item) => (
              <li key={item.conversation_id}>
                <button
                  type="button"
                  aria-current={
                    item.conversation_id === conversationId ? "true" : undefined
                  }
                  onClick={() => {
                    setConversationId(item.conversation_id);
                    idempotencyRef.current = newIdempotencyKey();
                    setChat(createChatViewState(idempotencyRef.current));
                    setFailure(null);
                  }}
                >
                  {displayText(item.title ?? item.conversation_id)}
                </button>
              </li>
            ))}
          </ul>

          <h2>Documents</h2>
          <p className={styles.muted}>
            Graph ready is never inferred from upload alone. Local signed_url is
            null until Phase 10 CloudFront. BM25 index/lag come from version
            status, not chat SSE.
          </p>
          <div className={styles.row}>
            <button
              type="button"
              onClick={() => uploadMutation.mutate()}
              disabled={meQuery.data?.upload_enabled !== true}
            >
              Reserve upload
            </button>
          </div>
          {meQuery.data?.upload_enabled !== true ? (
            <p className={styles.muted}>
              Upload control hidden as convenience only. Server still denies
              when upload_enabled is false.
            </p>
          ) : null}
          {uploadMutation.data ? (
            <p className={styles.muted} role="status">
              Reservation {displayText(uploadMutation.data.reservation_id)}.
              signed_url=
              {uploadMutation.data.signed_url === null
                ? "null (Phase 10)"
                : displayText(uploadMutation.data.signed_url)}
              . Finalize remains API-side.
            </p>
          ) : null}
          {uploadMutation.isError ? (
            <p className={styles.banner} data-kind="error" role="alert">
              Upload reserve rejected. Server authorization is authoritative.
            </p>
          ) : null}
          <ul className={styles.list}>
            {(documentsQuery.data ?? []).map((doc) => (
              <li key={doc.document_id}>
                <button
                  type="button"
                  aria-current={
                    doc.current_version_id === selectedVersionId ? "true" : undefined
                  }
                  disabled={doc.current_version_id === null}
                  onClick={() => {
                    if (doc.current_version_id !== null) {
                      setSelectedVersionId(doc.current_version_id);
                    }
                  }}
                >
                  {displayText(doc.title ?? doc.document_id)} —{" "}
                  {displayText(doc.visibility)}
                </button>
              </li>
            ))}
          </ul>
          {versionStatusQuery.data ? (
            <dl>
              <dt>Version status</dt>
              <dd>{displayText(versionStatusQuery.data.status)}</dd>
              <dt>Hybrid verified</dt>
              <dd>
                {displayText(versionStatusQuery.data.hybrid_verified_at ?? "not yet")}
              </dd>
              <dt>Retrieval eligible</dt>
              <dd>{versionStatusQuery.data.retrieval_eligible ? "yes" : "no"}</dd>
              <dt>Graph eligible</dt>
              <dd>
                {versionStatusQuery.data.document_graph_eligible ? "yes" : "no"}
              </dd>
              <dt>BM25</dt>
              <dd>{formatBm25Summary(versionStatusQuery.data.bm25)}</dd>
              <dt>Graph handoff</dt>
              <dd>
                {formatGraphHandoffSummary(versionStatusQuery.data.graph_handoff)}
              </dd>
            </dl>
          ) : null}
          {versionStatusQuery.data &&
          !versionStatusQuery.data.document_graph_eligible ? (
            <p className={styles.muted}>{graphNotReadyCopy(1)}</p>
          ) : null}
        </aside>

        <main className={styles.panel}>
          <h2>Auto chat (Composite)</h2>
          <p className={styles.muted}>
            Manual route selection is diagnostics-only and does not change
            admission. Handshake uses X-Client-Version {metaQuery.data?.min_client_version}.
          </p>
          <label>
            Message
            <textarea
              rows={4}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
            />
          </label>
          <div className={styles.row}>
            <button type="button" onClick={() => void send()}>
              Send
            </button>
            <button type="button" onClick={() => void reconnect()}>
              Reconnect
            </button>
            <button type="button" onClick={() => void cancel()}>
              Cancel
            </button>
          </div>
          <div className={styles.answer} aria-live="polite">
            {displayText(chat.answerText) || "No tokens yet."}
          </div>

          <h2>Diagnostics</h2>
          <dl>
            <dt>Requested route</dt>
            <dd>{displayText(chat.diagnostics.requestedRoute ?? chat.routeFamily ?? "—")}</dd>
            <dt>Effective route</dt>
            <dd>{displayText(chat.diagnostics.effectiveRoute ?? "—")}</dd>
            <dt>Corrected route</dt>
            <dd>{displayText(chat.diagnostics.correctedRoute ?? "none")}</dd>
            <dt>Cache</dt>
            <dd>{displayText(chat.diagnostics.cacheStatus ?? "—")}</dd>
            <dt>Coverage</dt>
            <dd>
              {chat.diagnostics.coverageScore === null
                ? "—"
                : String(chat.diagnostics.coverageScore)}
            </dd>
            <dt>Tools</dt>
            <dd>{chat.diagnostics.toolKeys.map(displayText).join(", ") || "none"}</dd>
            <dt>Stage</dt>
            <dd>
              {displayText(chat.stage ?? "—")} / {displayText(chat.status ?? "—")}
            </dd>
            <dt>Terminal</dt>
            <dd>{displayText(chat.terminal ?? "running")}</dd>
            <dt>Heartbeats</dt>
            <dd>{String(chat.diagnostics.heartbeatCount)}</dd>
            <dt>Unknown events</dt>
            <dd>{chat.diagnostics.unknownEvents.join(", ") || "none (ignored)"}</dd>
            <dt>Usage</dt>
            <dd>
              {String(chat.diagnostics.promptTokens)}/{String(chat.diagnostics.completionTokens)}{" "}
              tokens. Company total {String(usageQuery.data?.cost_usd ?? "—")} USD.
            </dd>
          </dl>
          {chat.diagnostics.limitationCodes.map((code) => (
            <p key={code} className={styles.banner} role="status">
              {limitationCopy(code)}
            </p>
          ))}
          {chat.diagnostics.limitationCodes.includes("graph_updating") ? (
            <p className={styles.muted}>{graphNotReadyCopy(0)}</p>
          ) : null}

          <h2>Citations</h2>
          <ul className={styles.list}>
            {(citationsQuery.data ?? []).map((citation) => {
              const urlRaw = citation.provenance.url;
              const url = typeof urlRaw === "string" && isSafeHttpUrl(urlRaw) ? urlRaw : null;
              return (
                <li key={citation.citation_id}>
                  [{citation.citation_index}] {displayText(citation.citation_id)}{" "}
                  {formatProvenance(citation.provenance)}
                  {citation.source_unavailable ? ` — ${limitationCopy("source_unavailable")}` : ""}
                  {url ? (
                    <>
                      {" "}
                      <a href={url} rel="noreferrer">
                        Open source
                      </a>
                    </>
                  ) : null}
                </li>
              );
            })}
          </ul>

          <h2>Feedback</h2>
          <label>
            Tag
            <select
              value={feedbackTag}
              onChange={(event) => setFeedbackTag(event.target.value as FeedbackTag)}
            >
              {FEEDBACK_TAGS.map((tag) => (
                <option key={tag} value={tag}>
                  {tag}
                </option>
              ))}
            </select>
          </label>
          <label>
            Comment
            <input
              value={feedbackComment}
              onChange={(event) => setFeedbackComment(event.target.value)}
            />
          </label>
          <button type="button" onClick={() => void sendFeedback()}>
            Submit thumbs-up feedback
          </button>
        </main>
      </div>
    </div>
  );
}
