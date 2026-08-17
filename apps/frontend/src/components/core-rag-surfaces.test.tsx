// @vitest-environment jsdom

import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { XSS_ENTITY, XSS_FILENAME } from "../lib/hostile-text-fixtures";
import { DOCUMENT_NOT_FOUND_COPY } from "../lib/citation-drawer";
import { CitationDrawer } from "./chat-app";
import { DocumentDetail } from "./document-detail";
import { SessionProvider } from "../lib/auth/session-provider";
import type { CitationResponse } from "../lib/types";

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
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
    storage: {
      from: () => ({
        upload: vi.fn(async () => ({ data: null, error: { message: "denied" } })),
      }),
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
      dependencies: [{ name: "paradedb", status: "down" }],
    })),
    fetchMe: vi.fn(async () => ({
      user_id: "u1",
      role: "member",
      authorization_version: 1,
      upload_enabled: true,
      mfa_enrolled: true,
    })),
    fetchDocument: vi.fn(async () => ({ ok: false, notFound: true })),
    listConversations: vi.fn(async () => []),
    listDocuments: vi.fn(async () => []),
    listTables: vi.fn(async () => []),
    fetchUsageMe: vi.fn(async () => ({
      scope: "me",
      cost_usd: "0",
      prompt_tokens: 0,
      completion_tokens: 0,
      usage_rows: 0,
    })),
    listCitations: vi.fn(async () => []),
    fetchVersionStatus: vi.fn(async () => null),
  };
});

afterEach(() => {
  cleanup();
});

/**
 * Wrap a surface with Query + session.
 *
 * @param ui - Element.
 * @returns Render result.
 */
function renderSurface(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SessionProvider>{ui}</SessionProvider>
    </QueryClientProvider>,
  );
}

describe("CitationDrawer", () => {
  it("renders hostile provenance as text and no privileged href", () => {
    const citation: CitationResponse = {
      citation_id: XSS_FILENAME,
      citation_index: 1,
      chunk_id: XSS_ENTITY,
      provenance: { url: "https://privileged.example/storage" },
      source_unavailable: true,
    };
    render(<CitationDrawer citation={citation} onClose={() => undefined} />);
    expect(screen.getByText(XSS_FILENAME, { exact: false })).toBeInTheDocument();
    expect(screen.getByText(XSS_ENTITY, { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /https:\/\// })).toBeNull();
    expect(document.querySelector("script")).toBeNull();
  });
});

describe("DocumentDetail 404", () => {
  it("shows Not found without a title leak", async () => {
    renderSurface(<DocumentDetail documentId="missing-id" />);
    expect(await screen.findByText(DOCUMENT_NOT_FOUND_COPY)).toBeInTheDocument();
    expect(screen.queryByText("SECRET")).toBeNull();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });
});
