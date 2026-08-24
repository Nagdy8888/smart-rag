// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { XSS_ENTITY, XSS_FILENAME } from "../lib/hostile-text-fixtures";
import { DOCUMENT_DELETE_UNAVAILABLE, DOCUMENT_NOT_FOUND_COPY, SOURCE_PREVIEW_UNAVAILABLE } from "../lib/citation-drawer";
import { CitationDrawer } from "./chat-app";
import { DocumentDetail } from "./document-detail";
import { DocumentLibrary } from "./document-library";
import { GraphExplorer } from "./graph-explorer";
import { TablesApp } from "./tables-app";
import { SessionProvider } from "../lib/auth/session-provider";
import { graphNotReadyCopy, limitationCopy } from "../lib/limitations";
import type { CitationResponse } from "../lib/types";

const fetchMe = vi.fn();
const fetchMeta = vi.fn();
const fetchReady = vi.fn();
const listDocuments = vi.fn();
const listTables = vi.fn();
const fetchVersionStatus = vi.fn();
const inspectGraph = vi.fn();
const analyzeTable = vi.fn();
const fetchDocument = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn() }),
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
    fetchMe: (...args: unknown[]) => fetchMe(...args),
    fetchMeta: (...args: unknown[]) => fetchMeta(...args),
    fetchReady: (...args: unknown[]) => fetchReady(...args),
    fetchDocument: (...args: unknown[]) => fetchDocument(...args),
    listConversations: vi.fn(async () => []),
    listDocuments: (...args: unknown[]) => listDocuments(...args),
    listTables: (...args: unknown[]) => listTables(...args),
    fetchUsageMe: vi.fn(async () => ({
      scope: "me",
      cost_usd: "0",
      prompt_tokens: 0,
      completion_tokens: 0,
      usage_rows: 0,
    })),
    listCitations: vi.fn(async () => []),
    fetchVersionStatus: (...args: unknown[]) => fetchVersionStatus(...args),
    inspectGraph: (...args: unknown[]) => inspectGraph(...args),
    analyzeTable: (...args: unknown[]) => analyzeTable(...args),
  };
});

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  fetchMeta.mockResolvedValue({
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  });
  fetchReady.mockResolvedValue({
    status: "ok",
    query_ready: true,
    detail: "ok",
    rate_limit_degraded: false,
    dependencies: [],
  });
  fetchMe.mockResolvedValue({
    user_id: "u1",
    role: "member",
    authorization_version: 1,
    upload_enabled: true,
  });
  fetchDocument.mockResolvedValue({ ok: false, notFound: true });
  listDocuments.mockResolvedValue([]);
  listTables.mockResolvedValue([]);
  fetchVersionStatus.mockResolvedValue(null);
  inspectGraph.mockResolvedValue({
    nodes: [],
    locators: [],
    limitations: [],
    row_count: 0,
    depth: 3,
  });
  analyzeTable.mockResolvedValue({
    table_id: "t",
    version_id: "v",
    document_id: "d",
    rows: [],
    source_ranges: [],
  });
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
    expect(screen.queryByText("ACME")).not.toBeInTheDocument();
    expect(document.querySelector("mark")).toBeNull();
    expect(screen.getByText(SOURCE_PREVIEW_UNAVAILABLE)).toBeInTheDocument();
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

describe("GraphExplorer ACL vs Graph Pending", () => {
  it("shows ACL blindness without unauthorized counts or titles", async () => {
    inspectGraph.mockResolvedValue({
      nodes: [
        {
          object_id: XSS_ENTITY,
          object_type: "entity",
          chunk_id: "c1",
          document_id: "d1",
          version_id: "v1",
          support: 1,
          hop: 1,
        },
      ],
      locators: [],
      limitations: [{ code: "graph_acl_blindness", count: 99 }],
      row_count: 1,
      depth: 3,
    });
    renderSurface(<GraphExplorer />);
    fireEvent.change(await screen.findByLabelText("Entity keys (comma-separated, max 12)"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
    expect(await screen.findAllByText(limitationCopy("graph_acl_blindness"))).not.toHaveLength(0);
    expect(screen.queryByText("99")).toBeNull();
    expect(screen.queryByText("SECRET TITLE")).toBeNull();
    expect(screen.getAllByText(XSS_ENTITY, { exact: false }).length).toBeGreaterThan(0);
    expect(document.querySelector("script")).toBeNull();
  });

  it("shows Graph Pending with authorized not-ready count only", async () => {
    inspectGraph.mockResolvedValue({
      nodes: [],
      locators: [],
      limitations: [{ code: "graph_pending", count: 2 }],
      row_count: 0,
      depth: 3,
    });
    renderSurface(<GraphExplorer />);
    fireEvent.change(await screen.findByLabelText("Entity keys (comma-separated, max 12)"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Inspect" }));
    expect(
      await screen.findByText(limitationCopy("graph_pending"), { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText(graphNotReadyCopy(2), { exact: false })).toBeInTheDocument();
    expect(screen.queryByText(/restricted/i)).toBeNull();
    expect(screen.queryByText(/ineligible/i)).toBeNull();
  });
});

describe("TablesApp source_ranges", () => {
  it("renders deterministic source_ranges and no client total or export", async () => {
    listTables.mockResolvedValue([
      {
        table_id: "11111111-1111-4111-8111-111111111111",
        document_id: "d1",
        version_id: "22222222-2222-4222-8222-222222222222",
        table_name: XSS_FILENAME,
        sheet_name: "Sheet1",
        row_count: 2,
        column_count: 2,
      },
    ]);
    analyzeTable.mockResolvedValue({
      table_id: "11111111-1111-4111-8111-111111111111",
      version_id: "22222222-2222-4222-8222-222222222222",
      document_id: "d1",
      rows: [{ amount: 1 }, { amount: 2 }],
      source_ranges: ["Sheet1!A1:B2"],
    });
    renderSurface(<TablesApp />);
    fireEvent.click(await screen.findByRole("button", { name: /Sheet1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText("Sheet1!A1:B2")).toBeInTheDocument();
    expect(screen.getByText(XSS_FILENAME, { exact: false })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    expect(screen.getByText(/Client total is null/)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});

describe("DocumentLibrary status and roles", () => {
  it("hides upload and crawl for a viewer", async () => {
    fetchMe.mockResolvedValue({
      user_id: "u-viewer",
      role: "viewer",
      authorization_version: 1,
      upload_enabled: true,
    });
    renderSurface(<DocumentLibrary />);
    expect(await screen.findByText(/Upload controls are hidden/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reserve, upload, finalize" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Enqueue crawl" })).toBeNull();
  });

  it("loads Graph Pending, BM25 none, and deletion_pending without a delete control", async () => {
    listDocuments.mockResolvedValue([
      {
        document_id: "doc-1",
        title: XSS_FILENAME,
        visibility: "company",
        current_version_id: "ver-1",
        visibility_generation: 1,
      },
    ]);
    fetchVersionStatus.mockResolvedValue({
      version: {
        version_id: "ver-1",
        document_id: "doc-1",
        status: "deletion_pending",
        retrieval_eligible: true,
        document_graph_eligible: false,
        hybrid_verified_at: null,
        bm25_verified_at: null,
        graph_handoff_at: null,
        retry_allowed: false,
        bm25: {
          active_index_version: null,
          index_schema_version: null,
          lag_seconds: 40,
          pending: 1,
          processing: 0,
          failed: 0,
          dead_letter: 0,
          retry_attempts: 0,
          verified_at: null,
        },
        graph_handoff: {
          pending: 1,
          processing: 0,
          completed: 0,
          failed: 0,
          dead_letter: 0,
        },
        scan: { result: "clean" },
        review: { declared_category: "allowed", attestation_policy_version: "2026-08-13" },
      },
      recent_jobs: [],
    });
    renderSurface(<DocumentLibrary />);
    fireEvent.click(await screen.findByRole("button", { name: "Load status" }));
    expect(await screen.findByText("Deletion pending")).toBeInTheDocument();
    expect(screen.getByText(/index=none/)).toBeInTheDocument();
    expect(screen.getByText(limitationCopy("graph_pending"), { exact: false })).toBeInTheDocument();
    expect(screen.getByText(DOCUMENT_DELETE_UNAVAILABLE)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /delete document/i })).toBeNull();
    expect(screen.getByText(XSS_FILENAME, { exact: false })).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
  });
});
