/**
 * Thin authenticated developer console. Not Stitch or production RAG chrome.
 *
 * Server authorization is authoritative. Hidden controls are convenience only.
 * Sign-in lives on `/login`. This surface stays on `/` after Auth.
 */

"use client";

import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Button } from "./ui/button";
import { CitationChip } from "./ui/citation-chip";
import { Input } from "./ui/input";
import { LimitationCallout } from "./ui/limitation-callout";
import { LiveRegion } from "./ui/live-region";
import { StatusBanner } from "./ui/status-banner";
import { StatusPill } from "./ui/status-pill";
import { Textarea } from "./ui/textarea";
import { HandshakeBanner } from "./auth/auth-screens";
import { ReadinessPanel, SignedOutageCopy } from "./readiness-panel";
import {
  cancelRun,
  createConversation,
  deleteConversation,
  fetchMe,
  fetchMeta,
  fetchReady,
  fetchUsageMe,
  fetchVersionStatus,
  listCitations,
  listConversations,
  listDocuments,
  reserveUpload,
  startOrResumeMessageStream,
  submitFeedback,
  resumeEventStream,
  type ApiAuth,
  type ApiFailure,
} from "../lib/api";
import { MFA_REQUIRED_BANNER, MFA_UPLOAD_DENIED, SESSION_REVOKED_BANNER } from "../lib/auth/copy";
import { useSession } from "../lib/auth/session-provider";
import {
  applyAdmission,
  createChatViewState,
  type ChatViewState,
} from "../lib/chat-view";
import { evaluatePaidHandshake, mayStartPaidPost } from "../lib/handshake";
import {
  formatBm25Summary,
  formatGraphHandoffSummary,
} from "../lib/ingestion-status";
import { graphNotReadyCopy, limitationCopy } from "../lib/limitations";
import { publicQueryKeys, sessionQueryKeys } from "../lib/query-keys";
import { apiFailureBanner } from "../lib/failure-copy";
import { displayText, formatProvenance, isSafeHttpUrl } from "../lib/safe-text";
import { consumeSse } from "../lib/sse-consume";
import { FEEDBACK_TAGS, type FeedbackTag } from "../lib/types";
import styles from "./developer-app.module.css";

function newIdempotencyKey(): string {
  return crypto.randomUUID();
}

/**
 * Collapse diagnostics on viewports below 801px; keep them open on desktop.
 *
 * @param children - Diagnostic definition list and related copy.
 * @returns Details element whose `open` tracks the desktop media query.
 */
function DiagnosticsDetails({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(true);
  useEffect(() => {
    const media = window.matchMedia("(min-width: 801px)");
    const sync = () => {
      setOpen(media.matches);
    };
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  return (
    <details
      className={styles.diagnostics}
      open={open}
      data-testid="diagnostics"
      onToggle={(event) => {
        setOpen(event.currentTarget.open);
      }}
    >
      <summary>Diagnostics</summary>
      {children}
    </details>
  );
}

/**
 * Render the thin developer UI for upload status, chat, citations,
 * feedback, and conversation deletion. Auth screens live on `/login`.
 *
 * @returns Developer console.
 */
export function DeveloperApp() {
  const queryClient = useQueryClient();
  const session = useSession();
  const accessToken = session.accessToken;
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
  const keys = sessionQueryKeys(accessToken);

  const metaQuery = useQuery({
    queryKey: publicQueryKeys.meta,
    queryFn: () => fetchMeta(),
  });

  const handshake = evaluatePaidHandshake(
    metaQuery.data ?? null,
    metaQuery.isPending ? "loading" : metaQuery.isError ? "error" : "ok",
  );

  const readyQuery = useQuery({
    queryKey: publicQueryKeys.ready,
    queryFn: () => fetchReady(),
    refetchInterval: 5000,
  });

  const meQuery = useQuery({
    queryKey: keys.me,
    queryFn: () => fetchMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const conversationsQuery = useQuery({
    queryKey: keys.conversations,
    queryFn: () => listConversations(auth as ApiAuth),
    enabled: auth !== null,
  });

  const documentsQuery = useQuery({
    queryKey: keys.documents,
    queryFn: () => listDocuments(auth as ApiAuth),
    enabled: auth !== null,
  });

  const versionStatusQuery = useQuery({
    queryKey: keys.versionStatus(selectedVersionId),
    queryFn: () => fetchVersionStatus(auth as ApiAuth, selectedVersionId as string),
    enabled: auth !== null && selectedVersionId !== null,
  });

  const usageQuery = useQuery({
    queryKey: keys.usage,
    queryFn: () => fetchUsageMe(auth as ApiAuth),
    enabled: auth !== null,
  });

  const citationsQuery = useQuery({
    queryKey: keys.citations(chat.runId),
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
    mutationFn: () => {
      if (!handshake.allowPaidPost) {
        throw new Error("handshake_blocked");
      }
      return reserveUpload(auth as ApiAuth, 1024, newIdempotencyKey());
    },
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

  const send = useCallback(async () => {
    if (auth === null || conversationId === null || draft.trim() === "") {
      return;
    }
    if (!mayStartPaidPost(handshake, chat)) {
      return;
    }
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    let current = chat;
    if (chat.runId === null || chat.terminal !== null) {
      if (idempotencyRef.current === null) {
        idempotencyRef.current = newIdempotencyKey();
      }
      current = createChatViewState(idempotencyRef.current);
      setChat(current);
      setFailure(null);
    }
    const started = await startOrResumeMessageStream(
      auth,
      conversationId,
      draft,
      {
        runId: current.runId,
        terminal: current.terminal,
        lastSequence: current.lastSequence,
        idempotencyKey: current.idempotencyKey,
      },
    );
    if (started.failure) {
      setFailure(started.failure);
      return;
    }
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
  }, [auth, chat, conversationId, draft, handshake]);

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

  const mfaRequired =
    meQuery.isError &&
    meQuery.error instanceof Error &&
    meQuery.error.message === "mfa_required";

  const sessionRevoked =
    meQuery.isError &&
    meQuery.error instanceof Error &&
    meQuery.error.message === "session_revoked";

  useEffect(() => {
    if (sessionRevoked) {
      void session.signOut();
    }
  }, [session, sessionRevoked]);

  if (!session.ready) {
    return (
      <div className={styles.shell}>
        <h1>Smart RAG developer console</h1>
        <p className={styles.muted}>Restoring session.</p>
      </div>
    );
  }

  if (accessToken === null) {
    return (
      <div className={styles.shell}>
        <h1>Smart RAG developer console</h1>
        <StatusBanner kind="info" role="status">
          Sign in to continue. Optimistic cookie checks are not authorization.
        </StatusBanner>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
        <ReadinessPanel ready={readyQuery.data} />
        <SignedOutageCopy />
      </div>
    );
  }

  if (mfaRequired) {
    return (
      <div className={styles.shell}>
        <header className={styles.row}>
          <h1>Smart RAG developer console</h1>
          <Button type="button" onClick={() => void session.signOut()}>
            Sign out
          </Button>
        </header>
        <StatusBanner kind="error" role="alert">
          {MFA_REQUIRED_BANNER}
        </StatusBanner>
        <p className={styles.muted}>
          <Link href="/mfa/challenge">MFA challenge</Link>
          {" · "}
          <Link href="/mfa/enroll">Enroll TOTP</Link>
        </p>
        <ReadinessPanel ready={readyQuery.data} />
        <SignedOutageCopy />
      </div>
    );
  }

  if (sessionRevoked || failure?.kind === "auth" && failure.detail === "session_revoked") {
    return (
      <div className={styles.shell}>
        <h1>Smart RAG developer console</h1>
        <StatusBanner kind="error" role="alert">
          {SESSION_REVOKED_BANNER}
        </StatusBanner>
        <p className={styles.muted}>
          <Link href="/login">Sign in</Link>
        </p>
      </div>
    );
  }

  const paidBlocked = !handshake.allowPaidPost;
  const sendDisabled = !mayStartPaidPost(handshake, chat);

  return (
    <div className={styles.shell}>
      <header className={styles.row}>
        <h1>Smart RAG developer console</h1>
        <p className={styles.muted}>
          Signed in as {displayText(meQuery.data?.role ?? "unknown")}{" "}
          {displayText(meQuery.data?.user_id ?? "")}. Server role is
          authoritative.
        </p>
        <Button type="button" onClick={() => void session.signOut()}>
          Sign out
        </Button>
      </header>
      <p className={styles.muted}>
        <Link href="/mfa/enroll">Enroll MFA</Link>
        {" · "}
        <Link href="/mfa/challenge">MFA challenge</Link>
        {" · "}
        <Link href="/invitations/accept">Accept invitation</Link>
      </p>

      <HandshakeBanner />

      {failure ? (
        <StatusBanner
          kind={failure.kind === "deleted" ? "info" : "error"}
          role={failure.kind === "deleted" ? "status" : "alert"}
        >
          {apiFailureBanner(failure)}
        </StatusBanner>
      ) : null}
      {deleteMutation.isSuccess && failure?.kind !== "deleted" ? (
        <StatusBanner kind="info" role="status">
          Conversation deleted. Reads, resume, and citations are denied. No
          source text is shown.
        </StatusBanner>
      ) : null}

      <div className={styles.grid}>
        <aside className={styles.panel}>
          <h2>Conversations</h2>
          <div className={styles.row}>
            <Button type="button" onClick={() => createMutation.mutate()}>
              New conversation
            </Button>
            <Button
              type="button"
              onClick={() => deleteMutation.mutate()}
              disabled={conversationId === null}
            >
              Delete conversation
            </Button>
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
            <Button
              type="button"
              onClick={() => uploadMutation.mutate()}
              disabled={meQuery.data?.upload_enabled !== true || paidBlocked}
            >
              Reserve upload
            </Button>
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
            <StatusBanner kind="error" role="alert">
              {uploadMutation.error instanceof Error &&
              uploadMutation.error.message === "mfa_required"
                ? MFA_UPLOAD_DENIED
                : "Upload reserve rejected. Server authorization is authoritative."}
            </StatusBanner>
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
                  <StatusPill status={doc.visibility} />
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

        <section className={styles.panel} aria-label="Auto chat">
          <h2>Auto chat (Composite)</h2>
          <p className={styles.muted}>
            Manual route selection is diagnostics-only and does not change
            admission. Handshake uses X-Client-Version {metaQuery.data?.min_client_version}.
          </p>
          <Textarea
            label="Message"
            rows={4}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            disabled={sendDisabled}
          />
          <div className={styles.row}>
            <Button
              type="button"
              variant="primary"
              onClick={() => void send()}
              disabled={sendDisabled}
            >
              Send
            </Button>
            <Button type="button" onClick={() => void reconnect()}>
              Reconnect
            </Button>
            <Button type="button" onClick={() => void cancel()}>
              Cancel
            </Button>
          </div>
          <LiveRegion aria-label="Answer tokens">
            {displayText(chat.answerText) || "No tokens yet."}
          </LiveRegion>

          <DiagnosticsDetails>
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
          </DiagnosticsDetails>
          {chat.diagnostics.limitationCodes.map((code) => (
            <LimitationCallout key={code}>
              {limitationCopy(code)}
            </LimitationCallout>
          ))}
          <ReadinessPanel ready={readyQuery.data} />
          <SignedOutageCopy />
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
                  <CitationChip
                    index={citation.citation_index}
                    citationId={citation.citation_id}
                    unavailable={citation.source_unavailable}
                    href={url}
                  />{" "}
                  {formatProvenance(citation.provenance)}
                  {citation.source_unavailable
                    ? ` — ${limitationCopy("source_unavailable")}`
                    : ""}
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
          <Input
            label="Comment"
            value={feedbackComment}
            onChange={(event) => setFeedbackComment(event.target.value)}
          />
          <Button type="button" onClick={() => void sendFeedback()}>
            Submit thumbs-up feedback
          </Button>
        </section>
      </div>
    </div>
  );
}
