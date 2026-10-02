// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { ChatApp } from "./chat/chat-app";
import {
  ClassifiedApiError,
  createConversation,
  generateConversationTitle,
  fetchMe,
  fetchMeta,
  listCitations,
  fetchCitationDetail,
  submitFeedback,
  fetchConversation,
  listConversations,
  fetchConversationMessages,
  loadConsoleReadiness,
} from "../lib/api";
import { conversationRailRenderCount } from "./chat/conversation-rail";
import { SESSION_REVOKED_BANNER } from "../lib/auth/copy";
import { SessionProvider } from "../lib/auth/session-provider";
import { CHAT_RUN_POINTER_KEY } from "../lib/chat-pointer";
import { MIXED_SCOPE_CLARIFICATION } from "../lib/answer-origin";
import { handshakeBelowMinCopy, QUERY_NOT_READY_COPY } from "../lib/handshake";
import { WEB_SEARCH_DISABLED_COPY } from "../lib/failure-copy";
import { limitationCopy } from "../lib/limitations";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
  }: {
    href: string;
    children: React.ReactNode;
  }) => <a href={href}>{children}</a>,
}));

vi.mock("../lib/auth/browser", () => ({
  createBrowserSupabase: () => ({
    auth: {
      getSession: vi.fn(async () => ({
        data: { session: { access_token: "jwt-token", user: { email: "a@b.test" } } },
      })),
      onAuthStateChange: vi.fn(() => ({
        data: { subscription: { unsubscribe: vi.fn() } },
      })),
      signOut: vi.fn(),
    },
  }),
}));

vi.mock("../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../lib/api")>("../lib/api");
  return {
    ...actual,
    fetchMeta: vi.fn(async () => ({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "9.0.0",
    })),
    fetchReady: vi.fn(async () => ({
      status: "degraded",
      query_ready: false,
      detail: "mock",
      rate_limit_degraded: false,
      dependencies: [],
    })),
    loadConsoleReadiness: vi.fn(async () => ({
      status: "degraded",
      query_ready: false,
      detail: "mock",
      rate_limit_degraded: false,
      dependencies: [{ name: "paradedb", status: "down" }],
    })),
    fetchMe: vi.fn(async () => ({
      user_id: "u1",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
    })),
    listConversations: vi.fn(async () => []),
    fetchConversation: vi.fn(async (_auth: unknown, conversationId: string) => ({
      conversation_id: conversationId,
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    })),
    createConversation: vi.fn(async () => ({
      conversation_id: "conv-created",
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    })),
    generateConversationTitle: vi.fn(async (_auth: unknown, conversationId: string) => ({
      conversation_id: conversationId,
      creator_user_id: "u1",
      title: "Hello summary",
      created_at: "2026-08-17T00:00:00Z",
    })),
    fetchUsageMe: vi.fn(async () => ({
      scope: "me",
      cost_usd: "0",
      prompt_tokens: 0,
      completion_tokens: 0,
      usage_rows: 0,
    })),
    listCitations: vi.fn(async () => []),
    fetchCitationDetail: vi.fn(async () => {
      throw new Error("citation detail should not prefetch");
    }),
    submitFeedback: vi.fn(async () => ({ feedback_id: "fb-1" })),
    fetchConversationMessages: vi.fn(async () => ({
      items: [],
      next_before_id: null,
    })),
  };
});

const defaultMeta = {
  api_version: "1",
  sse_schema_version: "1",
  min_client_version: "9.0.0",
};

beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
    callback(0);
    return 1;
  });
  vi.stubGlobal("cancelAnimationFrame", () => undefined);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.localStorage.clear();
  vi.mocked(fetchMeta).mockResolvedValue(defaultMeta);
  vi.mocked(listConversations).mockResolvedValue([]);
  vi.mocked(listCitations).mockResolvedValue([]);
  vi.mocked(fetchCitationDetail).mockReset();
  vi.mocked(submitFeedback).mockClear();
  vi.mocked(fetchConversationMessages).mockResolvedValue({
    items: [],
    next_before_id: null,
  });
  vi.mocked(createConversation).mockClear();
  vi.mocked(generateConversationTitle).mockClear();
  vi.mocked(fetchConversation).mockClear();
  vi.mocked(fetchConversation).mockImplementation(
    async (_auth: unknown, conversationId: string) => ({
      conversation_id: conversationId,
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    }),
  );
  vi.mocked(loadConsoleReadiness).mockResolvedValue({
    status: "degraded",
    query_ready: false,
    detail: "mock",
    rate_limit_degraded: false,
    dependencies: [{ name: "paradedb", status: "down" }],
  });
  vi.mocked(fetchMe).mockResolvedValue({
    user_id: "u1",
    role: "member",
    authorization_version: 1,
    upload_enabled: true,
  });
});

/**
 * Wrap ChatApp with providers.
 *
 * @param ui - Element.
 * @returns Render result.
 */
function renderChat(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

describe("ChatApp Auto chrome", () => {
  it("shows Answer source, blocks Send on handshake, and has no route send buttons", async () => {
    renderChat(<ChatApp />);
    const send = await screen.findByRole("button", { name: "Send" });
    expect(screen.getByRole("radiogroup", { name: "Answer source" })).toHaveAttribute(
      "data-value",
      "auto",
    );
    expect(screen.getByRole("radio", { name: "Auto" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByRole("radio", { name: "Company documents" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "General" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Web" })).toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Company files" })).toBeNull();
    expect(screen.queryByRole("radio", { name: "General knowledge" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Hybrid" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Combined" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Inspect" })).toBeNull();
    expect(send).toBeDisabled();
    expect(screen.getAllByText(handshakeBelowMinCopy()).length).toBeGreaterThan(0);
    expect(
      (await screen.findAllByText(limitationCopy("bm25_unavailable"))).length,
    ).toBeGreaterThan(0);
  });
});

const CONVERSATION = {
  conversation_id: "conv-1",
  creator_user_id: "u1",
  title: "Chat",
  created_at: "2026-08-17T00:00:00Z",
};

const ALLOWED_META = {
  api_version: "1",
  sse_schema_version: "1",
  min_client_version: "0.1.0",
};

/**
 * Build an SSE body for routing and limitation journeys.
 *
 * @returns Event-stream text with catalog frames plus one unknown event.
 */
function routingLimitationSse(): string {
  const limitations = [
    "temporal_graph_limitation",
    "bm25_unavailable",
    "graph_outage",
    "media_limitation",
    "negation_unresolved",
    "coverage_gap",
    "insufficient_evidence",
    "graph_acl_blindness",
    "graph_pending",
  ];
  const frames = [
    "event: heartbeat\nid: 1\ndata: {}\n\n",
    "event: future_metric\nid: 2\ndata: {\"n\":1}\n\n",
    'event: route_correction\nid: 3\ndata: {"from_route":"hybrid","to_route":"combined","reason":"relationship"}\n\n',
  ];
  limitations.forEach((code, index) => {
    frames.push(
      `event: limitation\nid: ${String(index + 4)}\ndata: {"code":"${code}"}\n\n`,
    );
  });
  frames.push(
    'event: citation_preview\nid: 19\ndata: {"citation_ids":["cite-1"],"snippet":"SECRET PASSAGE"}\n\n',
  );
  frames.push(
    'event: status\nid: 20\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
  );
  frames.push('event: token_delta\nid: 21\ndata: {"delta":"<script>x</script>"}\n\n');
  frames.push("event: completed\nid: 22\ndata: {}\n\n");
  return frames.join("");
}

/**
 * Stub FastAPI fetch for ChatApp (unmocked helpers use global fetch).
 *
 * @param options - Stream body and optional 404 resume.
 * @returns Fetch implementation.
 */
function stubChatFetch(options: {
  events?: string;
  resumeStatus?: number;
  cancelCalls?: string[];
  deleteCalls?: string[];
  messagePosts?: string[];
  messageBodies?: string[];
  messageStatus?: number;
  messageDetail?: string;
}): typeof fetch {
  return async (input, init) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "POST" && url.includes("/messages")) {
      options.messagePosts?.push(url);
      options.messageBodies?.push(String(init?.body ?? ""));
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Test-Role"]).toBeUndefined();
      const payload = JSON.parse(String(init?.body ?? "{}")) as {
        route?: unknown;
        search_scope?: string;
      };
      expect(payload.route).toBeUndefined();
      const requested =
        payload.search_scope === "web" ||
        payload.search_scope === "auto" ||
        payload.search_scope === "general_knowledge" ||
        payload.search_scope === "company_documents"
          ? payload.search_scope
          : "auto";
      if (options.messageStatus !== undefined && options.messageStatus >= 400) {
        return new Response(
          JSON.stringify({
            detail: options.messageDetail ?? "request_rejected",
          }),
          {
            status: options.messageStatus,
            headers: { "Content-Type": "application/json" },
          },
        );
      }
      return new Response(
        JSON.stringify({
          run_id: "run-1",
          stream_path: "/runs/run-1/events",
          reconnect: false,
          reservation_id: "res-1",
          route_family: requested === "web" ? "web_research" : "composite",
          status: "pending",
          requested_search_scope: requested,
        }),
        { status: 202, headers: { "Content-Type": "application/json" } },
      );
    }
    if (method === "GET" && url.includes("/events")) {
      if (options.resumeStatus === 404) {
        return new Response(JSON.stringify({ detail: "not_found" }), {
          status: 404,
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(options.events ?? "event: status\nid: 1\ndata: {\"stage\":\"verify_answer\",\"status\":\"verified\",\"phase\":\"completed\"}\n\nevent: token_delta\nid: 2\ndata: {\"delta\":\"Hi\"}\n\nevent: completed\nid: 3\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    }
    if (method === "POST" && url.includes("/cancel")) {
      options.cancelCalls?.push(url);
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Client-Version"]).toBeUndefined();
      return new Response(
        JSON.stringify({
          run_id: "run-1",
          conversation_id: "conv-1",
          creator_user_id: "u1",
          status: "cancelled",
          reservation_id: "res-1",
          created_at: "2026-08-17T00:00:00Z",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }
    if (method === "DELETE" && url.includes("/conversations/")) {
      options.deleteCalls?.push(url);
      return new Response(null, { status: 204 });
    }
    return new Response("{}", {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };
}

describe("ChatApp MFA removal and revoked session", () => {
  it("does not render MFA challenge or enroll links", async () => {
    renderChat(<ChatApp />);
    await screen.findByRole("button", { name: "Send" });
    expect(screen.queryByRole("link", { name: "MFA challenge" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Enroll TOTP" })).toBeNull();
    expect(screen.queryByLabelText(/recovery/i)).toBeNull();
  });

  it("shows session_revoked banner and signs out", async () => {
    vi.mocked(fetchMe).mockRejectedValue(new Error("session_revoked"));
    renderChat(<ChatApp />);
    expect(await screen.findByText(SESSION_REVOKED_BANNER)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });

  it("shows the session-rejected banner when /me is unauthorized", async () => {
    vi.mocked(fetchMe).mockRejectedValue(
      new ClassifiedApiError({
        kind: "auth",
        status: 401,
        detail: "unauthorized",
      }),
    );
    renderChat(<ChatApp />);
    expect(
      await screen.findByText(
        "Your session has ended. Sign in again.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send" })).toBeInTheDocument();
  });
});

describe("ChatApp SSE limitation families and reconnect", () => {
  beforeEach(() => {
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "degraded",
      query_ready: true,
      detail: "mock",
      rate_limit_degraded: false,
      dependencies: [{ name: "paradedb", status: "down" }],
    });
  });

  it("renders Auto POST limitation copy, unknown events, and citations without snippets", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-1",
        citation_index: 1,
        chunk_id: "chunk-1",
        provenance: { page_number: 3, snippet: "should already be stripped" },
        source_unavailable: false,
        document_title: null,
        pdf_page_number: 3,
        paragraph_index: 0,
      },
    ]);
    vi.stubGlobal("fetch", stubChatFetch({ events: routingLimitationSse() }));
    renderChat(<ChatApp />);
    await screen.findByRole("button", { name: "Send" });
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "What connected ACME?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findAllByText(limitationCopy("temporal_graph_limitation")),
    ).not.toHaveLength(0);
    expect(screen.getAllByText(limitationCopy("graph_outage")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(limitationCopy("media_limitation")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(limitationCopy("negation_unresolved")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(limitationCopy("coverage_gap")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(limitationCopy("graph_acl_blindness")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(limitationCopy("graph_pending")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Hybrid" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Combined" })).toBeNull();
    expect(await screen.findByText("<script>x</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByText("SECRET PASSAGE")).toBeNull();
    expect(await screen.findByRole("button", { name: "Citation 1, Source · PDF page 3" })).toBeInTheDocument();
    const diagnostics = screen.getByTestId("advanced-diagnostics");
    expect(diagnostics).toHaveTextContent("future_metric");
    expect(diagnostics).toHaveTextContent("Combined");
    expect(diagnostics).toHaveTextContent("Hybrid");
    expect(diagnostics).not.toHaveTextContent("Heartbeats");
    expect(diagnostics).not.toHaveTextContent("none (ignored)");
    expect(diagnostics).not.toHaveTextContent("verify_answer");
  });

  it("reconnect 404 shows deleted copy without source text", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const fetchImpl = stubChatFetch({
      events: "event: heartbeat\nid: 1\ndata: {}\n\n",
    });
    vi.stubGlobal("fetch", fetchImpl);
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("button", { name: "Reconnect" })).toBeInTheDocument();
    vi.stubGlobal("fetch", stubChatFetch({ resumeStatus: 404 }));
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    expect(
      await screen.findByText(
        "Conversation deleted. Reads, resume, and citations are denied. No source text is shown.",
      ),
    ).toBeInTheDocument();
  });

  it("Stop posts /runs/{id}/cancel without X-Client-Version", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const cancelCalls: string[] = [];
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        controller.enqueue(
          new TextEncoder().encode("event: heartbeat\nid: 1\ndata: {}\n\n"),
        );
      },
    });
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && url.includes("/messages")) {
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            stream_path: "/runs/run-1/events",
            reconnect: false,
            reservation_id: "res-1",
            route_family: "hybrid",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      if (method === "GET" && url.includes("/events")) {
        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      if (method === "POST" && url.includes("/cancel")) {
        cancelCalls.push(url);
        const headers = init?.headers as Record<string, string>;
        expect(headers["X-Client-Version"]).toBeUndefined();
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            conversation_id: "conv-1",
            creator_user_id: "u1",
            status: "cancelled",
            reservation_id: "res-1",
            created_at: "2026-08-17T00:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("{}", { status: 200 });
    };
    vi.stubGlobal("fetch", fetchImpl);
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Stop" });
    await user.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => {
      expect(cancelCalls).toEqual(["http://127.0.0.1:8000/runs/run-1/cancel"]);
    });
  });

  it("New clears an active run and its reconnect state", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(createConversation).mockResolvedValue({
      conversation_id: "conv-new",
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    });
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: "event: heartbeat\nid: 1\ndata: {}\n\n",
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findAllByText(/Reconnecting/)).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "New chat" }));

    await waitFor(() => {
      expect(createConversation).not.toHaveBeenCalled();
      expect(screen.queryAllByText(/Reconnecting/)).toHaveLength(0);
    });
    expect(screen.getByLabelText("Message")).toHaveValue("");
    expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
  });

  it("Delete conversation confirms before DELETE and Cancel sends zero requests", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const deleteCalls: string[] = [];
    vi.stubGlobal("fetch", stubChatFetch({ deleteCalls }));
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.click(screen.getByRole("button", { name: "Conversation actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(
      await screen.findByRole("dialog", { name: "Delete conversation?" }),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    });
    expect(deleteCalls).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog", { name: "Delete conversation?" })).toBeNull();
    expect(deleteCalls).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Conversation actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete" }));
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(
      await screen.findByText(
        "Conversation deleted. Reads, resume, and citations are denied. No source text is shown.",
      ),
    ).toBeInTheDocument();
    expect(deleteCalls).toEqual([
      "http://127.0.0.1:8000/conversations/conv-1",
    ]);
  });

  it("opens run details, sources, and feedback surfaces then restores the trigger", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    renderChat(<ChatApp />);
    const details = await screen.findByRole("button", { name: "Run details" });
    await user.click(details);
    expect(screen.getByRole("dialog", { name: "Run details" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Run details" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Sources (0)" }));
    expect(screen.getByRole("dialog", { name: "Sources (0)" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("button", { name: "Give feedback" })).toBeNull();
  });

  it("creates a conversation on first Send then admits one message", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([]);
    vi.mocked(createConversation).mockResolvedValue({
      conversation_id: "conv-created",
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    });
    const messagePosts: string[] = [];
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: "event: status\nid: 1\ndata: {\"stage\":\"verify_answer\",\"status\":\"verified\",\"phase\":\"completed\"}\n\nevent: token_delta\nid: 2\ndata: {\"delta\":\"Hi\"}\n\nevent: completed\nid: 3\ndata: {}\n\n",
        messagePosts,
      }),
    );
    renderChat(<ChatApp />);
    await screen.findByRole("button", { name: "Send" });
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(createConversation).toHaveBeenCalledTimes(1);
      expect(createConversation).toHaveBeenCalledWith(
        { accessToken: "jwt-token" },
        "hello",
      );
    });
    await waitFor(() => {
      expect(messagePosts).toEqual([
        "http://127.0.0.1:8000/conversations/conv-created/messages",
      ]);
    });
    await waitFor(() => {
      expect(generateConversationTitle).toHaveBeenCalledWith(
        { accessToken: "jwt-token" },
        "conv-created",
      );
    });
  });

  it("posts the selected Answer source and disables it during a live run", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([]);
    const messageBodies: string[] = [];
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events:
          'event: status\nid: 1\ndata: {"stage":"retrieve","status":"running","phase":"started"}\n\n',
        messagePosts: [],
        messageBodies,
      }),
    );
    renderChat(<ChatApp />);
    const source = await screen.findByRole("radiogroup", { name: "Answer source" });
    expect(source).toHaveAttribute("data-value", "auto");
    expect(screen.getByRole("radio", { name: "Auto" })).toBeEnabled();
    await user.click(screen.getByRole("radio", { name: "General" }));
    expect(source).toHaveAttribute("data-value", "general_knowledge");
    await user.type(screen.getByLabelText("Message"), "Parallel Tool Execution");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(messageBodies).toHaveLength(1);
    });
    expect(JSON.parse(messageBodies[0] ?? "{}")).toMatchObject({
      message: "Parallel Tool Execution",
      search_scope: "general_knowledge",
    });
    await waitFor(() => {
      expect(screen.getByRole("radio", { name: "Auto" })).toBeDisabled();
      expect(screen.getByRole("radio", { name: "General" })).toBeDisabled();
    });
  });

  it("keeps Send unused when conversation create fails", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(createConversation).mockReset();
    vi.mocked(createConversation).mockRejectedValue(new Error("create_failed"));
    const messagePosts: string[] = [];
    vi.stubGlobal("fetch", stubChatFetch({ messagePosts }));
    renderChat(<ChatApp />);
    await user.type(await screen.findByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(createConversation).toHaveBeenCalledTimes(1);
    });
    expect(messagePosts).toEqual([]);
    expect(screen.getByLabelText("Message")).toHaveValue("hello");
  });

  it("shows the session-rejected banner when conversation create is unauthorized", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(createConversation).mockReset();
    vi.mocked(createConversation).mockRejectedValue(
      new ClassifiedApiError({
        kind: "auth",
        status: 401,
        detail: "unauthorized",
      }),
    );
    const messagePosts: string[] = [];
    vi.stubGlobal("fetch", stubChatFetch({ messagePosts }));
    renderChat(<ChatApp />);
    await user.type(await screen.findByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText(
        "Your session has ended. Sign in again.",
      ),
    ).toBeInTheDocument();
    expect(messagePosts).toEqual([]);
  });
});


describe("ChatApp query_ready gate", () => {
  it("disables Send with query_ready copy while Hybrid remains the answering mode", async () => {
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    renderChat(<ChatApp />);
    expect(await screen.findByRole("button", { name: "Send" })).toBeDisabled();
    await waitFor(() => {
      expect(screen.getByText(QUERY_NOT_READY_COPY)).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Hybrid" })).toBeNull();
  });
});

describe("ChatApp Ask workspace", () => {
  it("shows the dual-mode empty state before a question is sent", async () => {
    renderChat(<ChatApp />);
    expect(
      await screen.findByText(
        "Ask about your documents",
      ),
    ).toBeInTheDocument();
  });

  it("hides citation chips for a general origin even when citations are listed", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-1",
        citation_index: 1,
        chunk_id: "chunk-1",
        provenance: {},
        source_unavailable: false,
      },
    ]);
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: [
          'event: answer_origin\nid: 1\ndata: {"origin":"general_knowledge"}\n\n',
          'event: citation_preview\nid: 2\ndata: {"citation_ids":["cite-1"]}\n\n',
          'event: status\nid: 3\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
          'event: token_delta\nid: 4\ndata: {"delta":"Paris is the capital of France."}\n\n',
          'event: usage\nid: 5\ndata: {"prompt_tokens":412,"completion_tokens":88}\n\n',
          "event: completed\nid: 6\ndata: {}\n\n",
        ].join(""),
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "capital of France");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText("Paris is the capital of France.")).toBeInTheDocument();
    expect(screen.getByTestId("answer-origin")).toHaveTextContent("General knowledge");
    expect(screen.getByTestId("answer-route")).toHaveTextContent("Composite");
    expect(screen.queryByTestId("answer-citations")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Citation 1" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sources (0)" })).toBeNull();
    expect(screen.getByTestId("answer-token-usage")).toHaveTextContent(
      "412 prompt · 88 completion",
    );
  });

  it("shows citation chips for a company origin and keeps the route pill separate", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-1",
        citation_index: 1,
        chunk_id: "chunk-1",
        provenance: { url: "https://storage.example/secret" },
        source_unavailable: false,
        source_kind: "company_document",
      },
    ]);
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: [
          'event: answer_origin\nid: 1\ndata: {"origin":"company_documents"}\n\n',
          'event: citation_preview\nid: 2\ndata: {"citation_ids":["cite-1"]}\n\n',
          'event: status\nid: 3\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
          'event: token_delta\nid: 4\ndata: {"delta":"The refund period is 30 days."}\n\n',
          "event: completed\nid: 5\ndata: {}\n\n",
        ].join(""),
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "What is our refund period?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("button", { name: /Citation 1/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Citation 1" })).toBeNull();
    expect(screen.getByTestId("answer-origin")).toHaveTextContent("Company documents");
    expect(screen.getByTestId("answer-route")).toHaveTextContent("Composite");
    expect(screen.getByRole("button", { name: "Sources (1)" })).toBeInTheDocument();
  });

  it("offers Web when meta disables it and still posts search_scope web", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const messageBodies: string[] = [];
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events:
          'event: status\nid: 1\ndata: {"stage":"web_search","status":"running","phase":"started"}\n\n',
        messagePosts: [],
        messageBodies,
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    const source = await screen.findByRole("radiogroup", { name: "Answer source" });
    expect(await screen.findByRole("radio", { name: "Web" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Web" }));
    expect(source).toHaveAttribute("data-value", "web");
    await user.type(screen.getByLabelText("Message"), "latest public briefing");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(messageBodies).toHaveLength(1);
    });
    expect(JSON.parse(messageBodies[0] ?? "{}")).toMatchObject({
      message: "latest public briefing",
      search_scope: "web",
    });
  });

  it("shows Web-disabled copy instead of limiter fail-closed", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        messageStatus: 503,
        messageDetail: "web_search_disabled",
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.click(await screen.findByRole("radio", { name: "Web" }));
    await user.type(screen.getByLabelText("Message"), "latest public briefing");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(WEB_SEARCH_DISABLED_COPY)).toBeInTheDocument();
    expect(screen.queryByText(/Limiter fail-closed/)).toBeNull();
  });

  it("offers Web when meta enables it and posts search_scope web", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue({
      ...ALLOWED_META,
      web_search_enabled: true,
    });
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const messageBodies: string[] = [];
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events:
          'event: status\nid: 1\ndata: {"stage":"web_search","status":"running","phase":"started"}\n\n',
        messagePosts: [],
        messageBodies,
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    const source = await screen.findByRole("radiogroup", { name: "Answer source" });
    expect(await screen.findByRole("radio", { name: "Web" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Web" }));
    expect(source).toHaveAttribute("data-value", "web");
    await user.type(screen.getByLabelText("Message"), "latest public briefing");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(messageBodies).toHaveLength(1);
    });
    expect(JSON.parse(messageBodies[0] ?? "{}")).toMatchObject({
      message: "latest public briefing",
      search_scope: "web",
    });
    expect(await screen.findAllByText("Searching…")).not.toHaveLength(0);
  });

  it("shows Web origin URL chips and keeps company citations non-clickable", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue({
      ...ALLOWED_META,
      web_search_enabled: true,
    });
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-web",
        citation_index: 1,
        chunk_id: null,
        provenance: {
          title: "Public briefing",
          url: "https://example.test/brief",
        },
        source_unavailable: false,
        source_kind: "web",
        web_source_id: "ws-1",
      },
    ]);
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: [
          'event: answer_origin\nid: 1\ndata: {"origin":"web"}\n\n',
          'event: citation_preview\nid: 2\ndata: {"citation_ids":["cite-web"]}\n\n',
          'event: status\nid: 3\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
          'event: token_delta\nid: 4\ndata: {"delta":"The briefing is public."}\n\n',
          "event: completed\nid: 5\ndata: {}\n\n",
        ].join(""),
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    expect(await screen.findByRole("radio", { name: "Web" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: "Web" }));
    await user.type(screen.getByLabelText("Message"), "public briefing");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const chip = await screen.findByRole("link", {
      name: "Citation 1, Public briefing",
    });
    expect(chip).toHaveAttribute("href", "https://example.test/brief");
    expect(chip).toHaveAttribute("rel", "noreferrer");
    expect(screen.getByTestId("answer-origin")).toHaveTextContent("Web");
    expect(screen.getByTestId("answer-route")).toHaveTextContent("Web research");
  });

  it("shows clarification and no citation chips for an ambiguous origin", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-1",
        citation_index: 1,
        chunk_id: "chunk-1",
        provenance: {},
        source_unavailable: false,
      },
    ]);
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: [
          'event: answer_origin\nid: 1\ndata: {"origin":"ambiguous"}\n\n',
          'event: citation_preview\nid: 2\ndata: {"citation_ids":["cite-1"]}\n\n',
          'event: status\nid: 3\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
          'event: token_delta\nid: 4\ndata: {"delta":"Please ask one question."}\n\n',
          "event: completed\nid: 5\ndata: {}\n\n",
        ].join(""),
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "France and refund");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(MIXED_SCOPE_CLARIFICATION)).toBeInTheDocument();
    expect(screen.getByTestId("answer-origin")).toHaveTextContent("Needs clarification");
    expect(screen.queryByTestId("answer-citations")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sources (0)" })).toBeNull();
  });

  it("exposes labeled Sessions and Conversation regions", async () => {
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    renderChat(<ChatApp />);
    expect(await screen.findByRole("button", { name: "Chat" })).toBeInTheDocument();
    expect(screen.getByTestId("sessions-rail")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Conversation" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Answer" })).toBeInTheDocument();
    expect(
      screen.getByRole("list", { name: "Sessions", hidden: true }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Chat" })).not.toHaveTextContent(
      "Older",
    );
    expect(screen.getByText("Older")).toBeInTheDocument();
    expect(document.querySelector('[role="option"]')).toBeNull();
    expect(document.querySelector('[role="option"] button')).toBeNull();
  });

  it("collapses the Sessions list without deleting conversations", async () => {
    const user = userEvent.setup();
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    renderChat(<ChatApp />);
    expect(await screen.findByRole("button", { name: "Chat" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Collapse sessions" }));
    expect(screen.queryByRole("button", { name: "Chat" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Expand sessions" }));
    expect(screen.getByRole("button", { name: "Chat" })).toBeInTheDocument();
  });

  it("New prevents a delayed reload recovery from restoring the old run", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(createConversation).mockResolvedValue({
      conversation_id: "conv-new",
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    });
    let resolveOldConversation:
      | ((value: typeof CONVERSATION) => void)
      | undefined;
    vi.mocked(fetchConversation).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveOldConversation = resolve;
        }),
    );
    sessionStorage.setItem(
      CHAT_RUN_POINTER_KEY,
      JSON.stringify({
        conversationId: CONVERSATION.conversation_id,
        runId: "run-old",
        lastSequence: 4,
      }),
    );
    renderChat(<ChatApp />);
    await waitFor(() => {
      expect(fetchConversation).toHaveBeenCalled();
    });

    await user.click(await screen.findByRole("button", { name: "New chat" }));
    resolveOldConversation?.(CONVERSATION);

    await waitFor(() => {
      expect(createConversation).not.toHaveBeenCalled();
      expect(screen.queryByRole("button", { name: "Stop" })).toBeNull();
    });
    expect(sessionStorage.getItem(CHAT_RUN_POINTER_KEY)).toBeNull();
  });

  it("fills the composer from a prompt chip without sending", async () => {
    const user = userEvent.setup();
    renderChat(<ChatApp />);
    const chipLabel =
      "Reproduce the cancel_order tool as a fenced Python code block from Building Applications with AI Agents.";
    await user.click(await screen.findByRole("button", { name: chipLabel }));
    expect(screen.getByLabelText("Message")).toHaveValue(chipLabel);
    expect(createConversation).not.toHaveBeenCalled();
  });

  it("shows the answer format gallery on an empty Ask stage", async () => {
    renderChat(<ChatApp />);
    expect(
      await screen.findByTestId("answer-format-gallery"),
    ).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Code" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
  });

  it("renders fetched transcript messages in ascending order", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(fetchConversationMessages).mockResolvedValue({
      items: [
        {
          message_id: "m2",
          role: "assistant",
          content: "Later answer",
          created_at: "2026-08-17T00:01:00Z",
        },
        {
          message_id: "m1",
          role: "user",
          content: "First question",
          created_at: "2026-08-17T00:00:00Z",
        },
      ],
      next_before_id: null,
    });
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await waitFor(() => {
      expect(fetchConversation).toHaveBeenCalled();
      expect(fetchConversationMessages).toHaveBeenCalled();
    });
    const first = screen.getByText("First question");
    const later = screen.getByText("Later answer");
    expect(first.compareDocumentPosition(later) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(
      screen.queryByText(
        "Continuing this session. Earlier messages are not available in this client.",
      ),
    ).toBeNull();
  });

  it("restores historical Sources from citation_count without N+1 detail", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(fetchConversationMessages).mockResolvedValue({
      items: [
        {
          message_id: "a1",
          role: "assistant",
          content: "Refunds close in 30 days.",
          created_at: "2026-08-17T00:01:00Z",
          run_id: "run-hist",
          citation_count: 2,
          source_kind: "company_document",
          citations: [],
        },
        {
          message_id: "u1",
          role: "user",
          content: "refunds?",
          created_at: "2026-08-17T00:00:00Z",
        },
      ],
      next_before_id: null,
    });
    vi.mocked(listCitations).mockResolvedValue([
      {
        citation_id: "cite-1",
        citation_index: 0,
        chunk_id: "c1",
        provenance: {},
        source_unavailable: false,
        document_title: "Policy",
        pdf_page_number: 3,
      },
    ]);
    vi.mocked(fetchCitationDetail).mockResolvedValue({
      citation_id: "cite-1",
      citation_index: 0,
      chunk_id: "c1",
      provenance: {},
      source_unavailable: false,
      document_title: "Policy",
      pdf_page_number: 3,
      evidence_excerpt: "close in 30 days",
    });
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    const turnSources = await screen.findByRole("button", { name: "Sources (2)" });
    expect(fetchCitationDetail).not.toHaveBeenCalled();
    await user.click(turnSources);
    await waitFor(() => {
      expect(listCitations).toHaveBeenCalledWith(
        { accessToken: "jwt-token" },
        "run-hist",
      );
    });
    expect(fetchCitationDetail).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: /Citation 0/ }));
    await waitFor(() => {
      expect(fetchCitationDetail).toHaveBeenCalledTimes(1);
    });
  });

  it("posts reload feedback to the settled transcript run, not a reconnect pointer", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    sessionStorage.setItem(
      CHAT_RUN_POINTER_KEY,
      JSON.stringify({
        conversationId: "conv-1",
        runId: "run-reconnect",
        lastSequence: 4,
      }),
    );
    vi.mocked(fetchConversationMessages).mockResolvedValue({
      items: [
        {
          message_id: "a1",
          role: "assistant",
          content: "Settled answer.",
          created_at: "2026-08-17T00:01:00Z",
          run_id: "run-settled",
          citation_count: 0,
        },
        {
          message_id: "u1",
          role: "user",
          content: "hello",
          created_at: "2026-08-17T00:00:00Z",
        },
      ],
      next_before_id: null,
    });
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.click(await screen.findByRole("button", { name: "Give feedback" }));
    await user.click(screen.getByRole("button", { name: "Submit feedback" }));
    await waitFor(() => {
      expect(submitFeedback).toHaveBeenCalledWith(
        { accessToken: "jwt-token" },
        "run-settled",
        true,
        "helpful answer",
        null,
      );
    });
    expect(submitFeedback).not.toHaveBeenCalledWith(
      expect.anything(),
      "run-reconnect",
      expect.anything(),
      expect.anything(),
      expect.anything(),
    );
  });

  it("shows Generating then Verifying then inserts the verified answer without a caret", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    const encoder = new TextEncoder();
    const streamCtl: { send: (chunk: string) => void; close: () => void } = {
      send() {},
      close() {},
    };
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamCtl.send = (chunk: string) => {
          controller.enqueue(encoder.encode(chunk));
        };
        streamCtl.close = () => {
          controller.close();
        };
      },
    });
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && url.includes("/messages")) {
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            stream_path: "/runs/run-1/events",
            reconnect: false,
            reservation_id: "res-1",
            route_family: "hybrid",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      if (method === "GET" && url.includes("/events")) {
        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return new Response("{}", { status: 200 });
    };
    vi.stubGlobal("fetch", fetchImpl);
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "Summarize the policy");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Stop" });
    expect(screen.getByLabelText("Message")).toHaveValue("");
    streamCtl.send(
      'event: status\nid: 1\ndata: {"stage":"generate_answer","status":"running","phase":"started"}\n\n',
    );
    expect((await screen.findAllByText("Generating…")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Verified policy summary.")).toBeNull();
    expect(document.querySelector(".typewriter, [data-caret]")).toBeNull();
    streamCtl.send(
      'event: status\nid: 2\ndata: {"stage":"verify_answer","status":"running","phase":"started"}\n\n',
    );
    expect((await screen.findAllByText("Verifying…")).length).toBeGreaterThan(0);
    expect(screen.queryByText("Verified policy summary.")).toBeNull();
    streamCtl.send(
      'event: status\nid: 3\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
    );
    streamCtl.send(
      'event: token_delta\nid: 4\ndata: {"delta":"Verified policy summary."}\n\n',
    );
    expect(await screen.findByText("Verified policy summary.")).toBeInTheDocument();
    streamCtl.send("event: completed\nid: 5\ndata: {}\n\n");
    streamCtl.close();
    expect(await screen.findByRole("button", { name: "Give feedback" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save to quiz" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Hybrid" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Combined" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Inspect" })).toBeNull();
  });

  it("shows one kept-token note when the stream errors after tokens", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events:
          'event: status\nid: 1\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\nevent: token_delta\nid: 2\ndata: {"delta":"Hi there."}\n\nevent: error\nid: 3\ndata: {"code":"run_failed"}\n\n',
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hi");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText("The run ended in an error. Received tokens are kept."),
    ).toBeInTheDocument();
    expect(await screen.findByText("Hi there.")).toBeInTheDocument();
    expect(screen.queryByText(/Something went wrong/)).toBeNull();
  });

  it("shows one generic reference when the stream errors with no tokens", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events: 'event: error\nid: 1\ndata: {"code":"run_failed"}\n\n',
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hi");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText("Something went wrong. Reference run-1."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Received tokens are kept/)).toBeNull();
  });

  it("does not treat a partial terminal as a protocol failure banner", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events:
          'event: status\nid: 1\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\nevent: token_delta\nid: 2\ndata: {"delta":"Hello."}\n\nevent: partial\nid: 3\ndata: {"reason":"verified_partial"}\n\n',
      }),
    );
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("button", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hi");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(
      await screen.findByText("Partial answer. Verified tokens are kept."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Run error/)).toBeNull();
    expect(screen.queryByText(/Something went wrong/)).toBeNull();
  });

  it("falls back to Untitled chat when the title is null", async () => {
    vi.mocked(listConversations).mockResolvedValue([
      {
        conversation_id: "conv-untitled",
        creator_user_id: "u1",
        title: null,
        created_at: "2026-08-17T00:00:00Z",
      },
    ]);
    renderChat(<ChatApp />);
    expect(await screen.findByRole("button", { name: "Untitled chat" })).toBeInTheDocument();
  });

  it("hides Reconnect, the stepper, and attachments copy while idle", async () => {
    renderChat(<ChatApp />);
    await screen.findByRole("button", { name: "Send" });
    expect(screen.queryByRole("button", { name: "Reconnect" })).toBeNull();
    expect(screen.queryByLabelText("Run pipeline")).toBeNull();
    expect(screen.queryByText(/Preparing/)).toBeNull();
    expect(screen.queryByText(/Attachments are not accepted/)).toBeNull();
    expect(screen.queryByText(/characters remaining/)).toBeNull();
  });

  it("does not re-render the Sessions rail while typing", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    renderChat(<ChatApp />);
    await screen.findByRole("button", { name: "Send" });
    await waitFor(() => {
      expect(vi.mocked(loadConsoleReadiness).mock.calls.length).toBeGreaterThan(0);
    });
    const before = conversationRailRenderCount.value;
    await user.type(screen.getByLabelText("Message"), "abcdefghij");
    expect(conversationRailRenderCount.value).toBe(before);
  });

  it("does not re-render the Sessions rail on token_delta", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    const encoder = new TextEncoder();
    const streamCtl: { send: (chunk: string) => void; close: () => void } = {
      send() {},
      close() {},
    };
    const stream = new ReadableStream<Uint8Array>({
      start(controller) {
        streamCtl.send = (chunk: string) => {
          controller.enqueue(encoder.encode(chunk));
        };
        streamCtl.close = () => {
          controller.close();
        };
      },
    });
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = (init?.method ?? "GET").toUpperCase();
      if (method === "POST" && url.includes("/messages")) {
        return new Response(
          JSON.stringify({
            run_id: "run-1",
            stream_path: "/runs/run-1/events",
            reconnect: false,
            reservation_id: "res-1",
            route_family: "hybrid",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      if (method === "GET" && url.includes("/events")) {
        return new Response(stream, {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      return new Response("{}", { status: 200 });
    };
    vi.stubGlobal("fetch", fetchImpl);
    renderChat(<ChatApp />);
    await user.type(await screen.findByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Stop" });
    const before = conversationRailRenderCount.value;
    streamCtl.send(
      'event: status\nid: 1\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\n',
    );
    streamCtl.send('event: token_delta\nid: 2\ndata: {"delta":"Hello tokens."}\n\n');
    expect(await screen.findByText("Hello tokens.")).toBeInTheDocument();
    expect(conversationRailRenderCount.value).toBe(before);
    streamCtl.close();
  });

  it("shows Sending… before a slow createConversation resolves", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    let resolveCreate: ((value: typeof CONVERSATION) => void) | undefined;
    vi.mocked(createConversation).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveCreate = resolve;
        }),
    );
    renderChat(<ChatApp />);
    await user.type(await screen.findByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByRole("button", { name: "Sending…" })).toBeInTheDocument();
    expect(screen.getByLabelText("Message")).toHaveValue("");
    expect(screen.getByText("hello")).toBeInTheDocument();
    resolveCreate?.({
      conversation_id: "conv-created",
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    });
  });
});

describe("ChatApp Save to quiz gating", () => {
  beforeEach(() => {
    vi.mocked(createConversation).mockResolvedValue({
      conversation_id: "conv-created",
      creator_user_id: "u1",
      title: "Chat",
      created_at: "2026-08-17T00:00:00Z",
    });
  });

  async function completeAsk(
    user: ReturnType<typeof userEvent.setup>,
  ): Promise<void> {
    vi.mocked(listConversations).mockResolvedValue([]);
    vi.mocked(loadConsoleReadiness).mockResolvedValue({
      status: "ok",
      query_ready: true,
      detail: "ready",
      rate_limit_degraded: false,
      dependencies: [],
    });
    vi.stubGlobal(
      "fetch",
      stubChatFetch({
        events:
          'event: status\nid: 1\ndata: {"stage":"verify_answer","status":"verified","phase":"completed"}\n\nevent: token_delta\nid: 2\ndata: {"delta":"Hi"}\n\nevent: completed\nid: 3\ndata: {}\n\n',
      }),
    );
    renderChat(<ChatApp />);
    await screen.findByRole("button", { name: "Send" });
    await user.type(screen.getByLabelText("Message"), "What is LCEL?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByRole("button", { name: "Give feedback" });
  }

  it("hides Save to quiz for members when the workspace capability is on", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue({
      ...ALLOWED_META,
      pdf_eval_workspace: true,
    });
    await completeAsk(user);
    expect(screen.getByRole("button", { name: "Give feedback" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save to quiz" })).toBeNull();
  });

  it("hides Save to quiz for viewers when the workspace capability is on", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue({
      ...ALLOWED_META,
      pdf_eval_workspace: true,
    });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u1",
      role: "viewer",
      authorization_version: 1,
      upload_enabled: false,
    });
    await completeAsk(user);
    expect(screen.queryByRole("button", { name: "Save to quiz" })).toBeNull();
  });

  it("hides Save to quiz for owners when the workspace capability is off", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u1",
      role: "owner",
      authorization_version: 1,
      upload_enabled: true,
    });
    await completeAsk(user);
    expect(screen.getByRole("button", { name: "Give feedback" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save to quiz" })).toBeNull();
  });

  it("shows Save to quiz beside Give feedback for owners when capability is on", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue({
      ...ALLOWED_META,
      pdf_eval_workspace: true,
    });
    vi.mocked(fetchMe).mockResolvedValue({
      user_id: "u1",
      role: "owner",
      authorization_version: 1,
      upload_enabled: true,
    });
    await completeAsk(user);
    expect(screen.getByRole("button", { name: "Give feedback" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save to quiz" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save to quiz" }));
    expect(screen.getByRole("dialog", { name: "Save to quiz" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "New case" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByRole("button", { name: "Give feedback" })).toBeInTheDocument();
  });
});
