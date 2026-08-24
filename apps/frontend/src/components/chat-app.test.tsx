// @vitest-environment jsdom

import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { ChatApp } from "./chat-app";
import {
  createConversation,
  fetchMe,
  fetchMeta,
  listCitations,
  listConversations,
} from "../lib/api";
import { MFA_REQUIRED_BANNER, SESSION_REVOKED_BANNER } from "../lib/auth/copy";
import { SessionProvider } from "../lib/auth/session-provider";
import { handshakeBelowMinCopy } from "../lib/handshake";
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
      mfa_enrolled: true,
    })),
    listConversations: vi.fn(async () => []),
    createConversation: vi.fn(async () => ({
      conversation_id: "conv-created",
      creator_user_id: "u1",
      title: "Chat",
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
  };
});

const defaultMeta = {
  api_version: "1",
  sse_schema_version: "1",
  min_client_version: "9.0.0",
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.mocked(fetchMeta).mockResolvedValue(defaultMeta);
  vi.mocked(listConversations).mockResolvedValue([]);
  vi.mocked(listCitations).mockResolvedValue([]);
  vi.mocked(createConversation).mockClear();
  vi.mocked(fetchMe).mockResolvedValue({
    user_id: "u1",
    role: "member",
    authorization_version: 1,
    upload_enabled: true,
    mfa_enrolled: true,
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
  it("shows Auto, blocks Send on handshake, and has no route send buttons", async () => {
    renderChat(<ChatApp />);
    const send = await screen.findByRole("button", { name: "Send" });
    expect(screen.getByRole("heading", { name: "Auto chat" })).toBeInTheDocument();
    expect(screen.getByTestId("auto-label")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Hybrid" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Combined" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Inspect" })).toBeNull();
    expect(send).toBeDisabled();
    expect(screen.getAllByText(handshakeBelowMinCopy()).length).toBeGreaterThan(0);
    expect(
      screen.getAllByText(limitationCopy("bm25_unavailable")).length,
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
    'event: citation_preview\nid: 20\ndata: {"citation_ids":["cite-1"],"snippet":"SECRET PASSAGE"}\n\n',
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
}): typeof fetch {
  return async (input, init) => {
    const url = String(input);
    const method = (init?.method ?? "GET").toUpperCase();
    if (method === "POST" && url.includes("/messages")) {
      options.messagePosts?.push(url);
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Test-Role"]).toBeUndefined();
      expect(JSON.parse(String(init?.body ?? "{}")).route).toBeUndefined();
      return new Response(
        JSON.stringify({
          run_id: "run-1",
          stream_path: "/runs/run-1/events",
          reconnect: false,
          reservation_id: "res-1",
          route_family: "composite",
          status: "pending",
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
      return new Response(options.events ?? "event: completed\nid: 1\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    }
    if (method === "POST" && url.includes("/cancel")) {
      options.cancelCalls?.push(url);
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Client-Version"]).toBeUndefined();
      return new Response(null, { status: 204 });
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

describe("ChatApp MFA and revoked session", () => {
  it("shows MFA required banner and has no recovery-code control", async () => {
    vi.mocked(fetchMe).mockRejectedValue(new Error("mfa_required"));
    renderChat(<ChatApp />);
    expect(await screen.findAllByText(MFA_REQUIRED_BANNER)).not.toHaveLength(0);
    expect(screen.getByRole("link", { name: "MFA challenge" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/recovery/i)).toBeNull();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });

  it("shows session_revoked banner and signs out", async () => {
    vi.mocked(fetchMe).mockRejectedValue(new Error("session_revoked"));
    renderChat(<ChatApp />);
    expect(await screen.findByText(SESSION_REVOKED_BANNER)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sign in" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send" })).toBeNull();
  });
});

describe("ChatApp SSE limitation families and reconnect", () => {
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
      },
    ]);
    vi.stubGlobal("fetch", stubChatFetch({ events: routingLimitationSse() }));
    renderChat(<ChatApp />);
    await screen.findByRole("heading", { name: "Auto chat" });
    await user.click(await screen.findByRole("option", { name: "Chat" }));
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
    expect(screen.getByText("<script>x</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(screen.queryByText("SECRET PASSAGE")).toBeNull();
    expect(await screen.findByRole("button", { name: "Citation 1" })).toBeInTheDocument();
    const diagnostics = screen.getByTestId("advanced-diagnostics");
    expect(diagnostics).toHaveTextContent("future_metric");
    expect(diagnostics).toHaveTextContent("combined");
  });

  it("reconnect 404 shows deleted copy without source text", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const fetchImpl = stubChatFetch({
      events: "event: heartbeat\nid: 1\ndata: {}\n\nevent: completed\nid: 2\ndata: {}\n\n",
    });
    vi.stubGlobal("fetch", fetchImpl);
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("option", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await screen.findByText("completed", { exact: false });
    vi.stubGlobal("fetch", stubChatFetch({ resumeStatus: 404 }));
    await user.click(screen.getByRole("button", { name: "Reconnect" }));
    expect(
      await screen.findByText(
        "Conversation deleted. Reads, resume, and citations are denied. No source text is shown.",
      ),
    ).toBeInTheDocument();
  });

  it("Cancel posts /runs/{id}/cancel without X-Client-Version", async () => {
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
        return new Response(null, { status: 204 });
      }
      return new Response("{}", { status: 200 });
    };
    vi.stubGlobal("fetch", fetchImpl);
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("option", { name: "Chat" }));
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(screen.getByTestId("advanced-diagnostics")).toHaveTextContent("1");
    });
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => {
      expect(cancelCalls).toEqual(["http://127.0.0.1:8000/runs/run-1/cancel"]);
    });
  });

  it("Delete conversation issues DELETE and shows deleted copy", async () => {
    const user = userEvent.setup();
    vi.mocked(fetchMeta).mockResolvedValue(ALLOWED_META);
    vi.mocked(listConversations).mockResolvedValue([CONVERSATION]);
    const deleteCalls: string[] = [];
    vi.stubGlobal("fetch", stubChatFetch({ deleteCalls }));
    renderChat(<ChatApp />);
    await user.click(await screen.findByRole("option", { name: "Chat" }));
    await user.click(screen.getByRole("button", { name: "Conversation actions" }));
    await user.click(screen.getByRole("menuitem", { name: "Delete conversation" }));
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
    await user.click(screen.getByRole("button", { name: "Feedback details" }));
    expect(screen.getByRole("combobox", { name: "Tag" })).toBeInTheDocument();
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
        events: "event: completed\nid: 1\ndata: {}\n\n",
        messagePosts,
      }),
    );
    renderChat(<ChatApp />);
    await screen.findByRole("heading", { name: "Auto chat" });
    await user.type(screen.getByLabelText("Message"), "hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(createConversation).toHaveBeenCalledTimes(1);
    });
    await waitFor(() => {
      expect(messagePosts).toEqual([
        "http://127.0.0.1:8000/conversations/conv-created/messages",
      ]);
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
  });
});
