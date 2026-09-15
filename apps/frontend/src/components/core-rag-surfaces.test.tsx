// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { XSS_ENTITY, XSS_FILENAME } from "../lib/hostile-text-fixtures";
import { DOCUMENT_NOT_FOUND_COPY, SOURCE_PREVIEW_UNAVAILABLE } from "../lib/citation-drawer";
import { CitationDrawer } from "./chat/chat-app";
import { CitationSheet } from "./chat/citation-sheet";
import { DocumentDetail } from "./documents/document-detail";
import { DocumentLibrary } from "./documents/document-library";
import { GraphExplorer } from "./graph/graph-explorer";
import { TablesApp } from "./tables/tables-app";
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
const searchGraphEntities = vi.fn();
const analyzeTable = vi.fn();
const fetchDocument = vi.fn();
const deleteDocument = vi.fn();

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
    deleteDocument: (...args: unknown[]) => deleteDocument(...args),
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
    searchGraphEntities: (...args: unknown[]) => searchGraphEntities(...args),
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
  deleteDocument.mockResolvedValue(undefined);
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
  searchGraphEntities.mockResolvedValue([]);
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

  it("shows book title, PDF page, and supporting passage", () => {
    const citation: CitationResponse = {
      citation_id: "cite-1",
      citation_index: 0,
      chunk_id: "chunk-1",
      provenance: {
        document_title: "Building applications with AI agents",
        page_number: 12,
        page_label: "12",
        section_path: ["Parallel Tool Execution"],
      },
      source_unavailable: false,
      document_title: "Building applications with AI agents",
      pdf_page_number: 129,
      evidence_excerpt: "Parallel tool execution reduces latency.",
    };
    render(<CitationDrawer citation={citation} onClose={() => undefined} />);
    expect(
      screen.getByRole("heading", {
        name: "Building applications with AI agents — PDF page 129",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("Building applications with AI agents")).toBeInTheDocument();
    expect(screen.getByText("129")).toBeInTheDocument();
    expect(screen.getByText("Parallel Tool Execution")).toBeInTheDocument();
    expect(
      screen.getByText("Parallel tool execution reduces latency."),
    ).toBeInTheDocument();
    expect(screen.queryByText(SOURCE_PREVIEW_UNAVAILABLE)).not.toBeInTheDocument();
  });

  it("renders hostile excerpt as text and keeps tab focus in the drawer", async () => {
    const user = userEvent.setup();
    const citation: CitationResponse = {
      citation_id: "cite-x",
      citation_index: 0,
      chunk_id: "chunk-x",
      provenance: {},
      source_unavailable: false,
      document_title: "<img src=x onerror=alert(1)>",
      pdf_page_number: 25,
      evidence_excerpt: "<script>alert(1)</script>",
    };
    render(<CitationDrawer citation={citation} onClose={() => undefined} />);
    expect(screen.getByText("<script>alert(1)</script>")).toBeInTheDocument();
    expect(document.querySelector("script")).toBeNull();
    expect(document.querySelector("img")).toBeNull();
    const dialog = screen.getByRole("dialog");
    await user.tab();
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  it("marks Arabic supporting passage as dir=auto", () => {
    const citation: CitationResponse = {
      citation_id: "cite-ar",
      citation_index: 0,
      chunk_id: "chunk-ar",
      provenance: {},
      source_unavailable: false,
      document_title: "الدليل",
      pdf_page_number: 3,
      evidence_excerpt: "مدة الاسترداد ثلاثون يوماً.",
    };
    render(<CitationDrawer citation={citation} onClose={() => undefined} />);
    expect(screen.getByText("مدة الاسترداد ثلاثون يوماً.").closest("span")).toHaveAttribute(
      "dir",
      "auto",
    );
  });
});

describe("CitationSheet", () => {
  it("lists page labels and does not repeat citation UUIDs", () => {
    render(
      <CitationSheet
        open
        onClose={() => undefined}
        citations={[
          {
            citation_id: "a035e243-03dd-4987-b7ed-fe00c0b9336c",
            citation_index: 0,
            chunk_id: "a035e243-03dd-4987-b7ed-fe00c0b9336c",
            provenance: { page_number: 129, document_title: "AI agents" },
            source_unavailable: false,
            document_title: "AI agents",
            pdf_page_number: 129,
          },
        ]}
        hrefForCitation={() => undefined}
        onSelectCitation={() => undefined}
      />,
    );
    expect(
      screen.getByRole("button", { name: "Citation 0, AI agents · PDF page 129" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("a035e243-03dd-4987-b7ed-fe00c0b9336c"),
    ).not.toBeInTheDocument();
    expect(screen.getByText(SOURCE_PREVIEW_UNAVAILABLE)).toBeInTheDocument();
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
    searchGraphEntities.mockResolvedValue([
      {
        object_id: "acme",
        object_type: "entity",
        chunk_id: "c1",
        document_id: "d1",
        version_id: "v1",
        support: 1,
      },
    ]);
    renderSurface(<GraphExplorer />);
    fireEvent.change(await screen.findByLabelText("Search entities"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByRole("button", { name: /acme/i }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect graph" }));
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
    searchGraphEntities.mockResolvedValue([
      {
        object_id: "acme",
        object_type: "entity",
        chunk_id: "c1",
        document_id: "d1",
        version_id: "v1",
        support: 1,
      },
    ]);
    renderSurface(<GraphExplorer />);
    fireEvent.change(await screen.findByLabelText("Search entities"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    fireEvent.click(await screen.findByRole("button", { name: /acme/i }));
    fireEvent.click(screen.getByRole("button", { name: "Inspect graph" }));
    expect(
      await screen.findAllByText(limitationCopy("graph_pending"), { exact: false }),
    ).not.toHaveLength(0);
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
    fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    fireEvent.change(screen.getByLabelText("Filter column"), {
      target: { value: "amount" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    fireEvent.click(await screen.findByRole("button", { name: "View provenance" }));
    expect(await screen.findByText("Sheet1!A1:B2")).toBeInTheDocument();
    expect(screen.getAllByText(XSS_FILENAME, { exact: false }).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    expect(screen.queryByText(/Client total is null/)).toBeNull();
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
    expect(await screen.findByLabelText("Filter by name")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Import source" })).toBeNull();
    expect(screen.queryByText(/Upload controls are hidden/)).toBeNull();
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
        created_at: "2026-08-24T00:00:00Z",
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
    expect(await screen.findAllByText("Deletion pending")).not.toHaveLength(0);
    fireEvent.click((await screen.findAllByRole("button", { name: "Document actions" }))[0]);
    fireEvent.click(screen.getByRole("menuitem", { name: "View processing" }));
    expect(await screen.findByRole("heading", { name: "Processing" })).toBeInTheDocument();
    expect(screen.getByText("Search index waiting")).toBeInTheDocument();
    expect(screen.getByText("Graph handoff waiting")).toBeInTheDocument();
    expect(screen.queryByText(/index=none/)).toBeNull();
    expect(screen.queryByText(limitationCopy("graph_pending"))).toBeNull();
    expect(screen.queryByText(/Document deletion is not available/i)).toBeNull();
    fireEvent.click(screen.getAllByRole("button", { name: "Document actions" })[0]);
    expect(screen.queryByRole("menuitem", { name: "Delete" })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete document/i })).toBeNull();
    expect(screen.getAllByText(XSS_FILENAME, { exact: false }).length).toBeGreaterThan(0);
    expect(document.querySelector("img")).toBeNull();
  });
});
