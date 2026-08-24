// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { DocumentDetail } from "./document-detail";
import { DocumentLibrary } from "./document-library";
import { SessionProvider } from "../../lib/auth/session-provider";
import { ClassifiedApiError } from "../../lib/api";
import { XSS_FILENAME } from "../../lib/hostile-text-fixtures";
import { ingestionStatusIsTerminal } from "./ingestion-status";

const fetchMe = vi.fn();
const fetchMeta = vi.fn();
const listDocuments = vi.fn();
const listTables = vi.fn();
const fetchVersionStatus = vi.fn();
const fetchDocument = vi.fn();
const deleteDocument = vi.fn();
const reserveUpload = vi.fn();
const finalizeUpload = vi.fn();
const enqueueWebsiteCrawl = vi.fn();
const retryIngestionJob = vi.fn();
const uploadReservedObject = vi.fn();
const routerPush = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/documents",
  useSearchParams: () => new URLSearchParams(),
  useRouter: () => ({ push: routerPush, replace: vi.fn(), prefetch: vi.fn() }),
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

vi.mock("../../lib/auth/browser", () => ({
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
        upload: vi.fn(async () => ({ data: {}, error: null })),
      }),
    },
  }),
}));

vi.mock("../../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../../lib/upload-client", async () => {
  const actual = await vi.importActual<typeof import("../../lib/upload-client")>(
    "../../lib/upload-client",
  );
  return {
    ...actual,
    sha256Hex: vi.fn(async () => "a".repeat(64)),
    uploadReservedObject: (...args: unknown[]) => uploadReservedObject(...args),
  };
});

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    fetchMe: (...args: unknown[]) => fetchMe(...args),
    fetchMeta: (...args: unknown[]) => fetchMeta(...args),
    fetchDocument: (...args: unknown[]) => fetchDocument(...args),
    deleteDocument: (...args: unknown[]) => deleteDocument(...args),
    listDocuments: (...args: unknown[]) => listDocuments(...args),
    listTables: (...args: unknown[]) => listTables(...args),
    fetchVersionStatus: (...args: unknown[]) => fetchVersionStatus(...args),
    reserveUpload: (...args: unknown[]) => reserveUpload(...args),
    finalizeUpload: (...args: unknown[]) => finalizeUpload(...args),
    enqueueWebsiteCrawl: (...args: unknown[]) => enqueueWebsiteCrawl(...args),
    retryIngestionJob: (...args: unknown[]) => retryIngestionJob(...args),
  };
});

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  routerPush.mockReset();
  fetchMe.mockReset();
  fetchMeta.mockReset();
  listDocuments.mockReset();
  listTables.mockReset();
  fetchVersionStatus.mockReset();
  fetchDocument.mockReset();
  deleteDocument.mockReset();
  reserveUpload.mockReset();
  finalizeUpload.mockReset();
  enqueueWebsiteCrawl.mockReset();
  retryIngestionJob.mockReset();
  uploadReservedObject.mockReset();
  fetchMeta.mockResolvedValue({
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  });
  fetchMe.mockResolvedValue({
    user_id: "u1",
    role: "owner",
    authorization_version: 1,
    upload_enabled: true,
  });
  listDocuments.mockResolvedValue([]);
  listTables.mockResolvedValue([]);
  fetchVersionStatus.mockResolvedValue(null);
  fetchDocument.mockResolvedValue({ ok: false, notFound: true });
  deleteDocument.mockResolvedValue(undefined);
  reserveUpload.mockResolvedValue({
    reservation_id: "res-1",
    storage_bucket: "quarantine",
    storage_path: "user/res/",
    expires_at: "2026-08-24T00:00:00Z",
    signed_url: null,
    upload_method: "supabase_storage_jwt",
  });
  finalizeUpload.mockResolvedValue({
    reservation_id: "res-1",
    document_id: "doc-new",
    version_id: "ver-new",
    job_id: "job-new",
  });
  enqueueWebsiteCrawl.mockResolvedValue({
    document_id: "doc-crawl",
    version_id: "ver-crawl",
    source_id: "src-crawl",
    approval_id: "appr-crawl",
    job_id: "job-crawl",
  });
  retryIngestionJob.mockResolvedValue({
    job_id: "job-1",
    status: "queued",
    detail: "ok",
  });
  uploadReservedObject.mockResolvedValue({ ok: true, error: null });
});

/**
 * Wrap a documents surface with Query + session.
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

describe("ingestionStatusIsTerminal", () => {
  it("stops polling on hybrid_ready, graph terminals, failed, and deletion_pending", () => {
    expect(ingestionStatusIsTerminal("scanning")).toBe(false);
    expect(ingestionStatusIsTerminal("hybrid_ready")).toBe(true);
    expect(ingestionStatusIsTerminal("graph_ready")).toBe(true);
    expect(ingestionStatusIsTerminal("graph_ineligible")).toBe(true);
    expect(ingestionStatusIsTerminal("failed")).toBe(true);
    expect(ingestionStatusIsTerminal("deletion_pending")).toBe(true);
  });
});

describe("DocumentLibrary upload", () => {
  it("completes reserve, storage upload, and finalize with one idempotency key", async () => {
    renderSurface(<DocumentLibrary />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Import source" }))[0]);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["hello"], XSS_FILENAME, { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => {
      expect(finalizeUpload).toHaveBeenCalled();
    });
    expect(reserveUpload).toHaveBeenCalledTimes(1);
    expect(uploadReservedObject).toHaveBeenCalled();
    const reserveKey = reserveUpload.mock.calls[0]?.[2];
    const finalizeBody = finalizeUpload.mock.calls[0]?.[1] as { idempotency_key: string };
    expect(finalizeBody.idempotency_key).toBe(reserveKey);
    expect(await screen.findByText(/doc-new/)).toBeInTheDocument();
    expect(listDocuments.mock.calls.length).toBeGreaterThan(1);
  });

  it("disables Upload when the paid handshake is blocked", async () => {
    fetchMeta.mockResolvedValue({
      api_version: "1",
      sse_schema_version: "1",
      min_client_version: "9.0.0",
    });
    renderSurface(<DocumentLibrary />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Import source" }))[0]);
    expect(screen.getByRole("button", { name: "Upload" })).toBeDisabled();
    expect(reserveUpload).not.toHaveBeenCalled();
  });

  it("shows a failure banner when finalize rejects and keeps the same retry key", async () => {
    finalizeUpload.mockRejectedValueOnce(new Error("upload_finalize_rejected"));
    renderSurface(<DocumentLibrary />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Import source" }))[0]);
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await userEvent.upload(input, new File(["hello"], "policy.pdf", { type: "application/pdf" }));
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    expect(await screen.findByText(/Upload rejected/)).toBeInTheDocument();
    const firstKey = reserveUpload.mock.calls[0]?.[2];
    fireEvent.click(screen.getByRole("button", { name: "Upload" }));
    await waitFor(() => {
      expect(reserveUpload).toHaveBeenCalledTimes(2);
    });
    expect(reserveUpload.mock.calls[1]?.[2]).toBe(firstKey);
  });
});

describe("DocumentLibrary crawl", () => {
  it("enqueues a crawl and shows created ids", async () => {
    renderSurface(<DocumentLibrary />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Import source" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "Website" }));
    fireEvent.change(screen.getByLabelText("Start URL"), {
      target: { value: "https://example.com/docs" },
    });
    fireEvent.change(screen.getByLabelText("Approved domain"), {
      target: { value: "example.com" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Add website" }));
    expect(await screen.findByText(/doc-crawl/)).toBeInTheDocument();
    expect(enqueueWebsiteCrawl.mock.calls[0]?.[1]).toMatchObject({
      start_url: "https://example.com/docs",
      approved_domain: "example.com",
    });
  });

  it("shows the 403 crawl banner without hiding that the server denied the call", async () => {
    enqueueWebsiteCrawl.mockRejectedValue(
      new ClassifiedApiError({ kind: "auth", status: 403, detail: "forbidden" }),
    );
    renderSurface(<DocumentLibrary />);
    fireEvent.click((await screen.findAllByRole("button", { name: "Import source" }))[0]);
    fireEvent.click(screen.getByRole("button", { name: "Website" }));
    fireEvent.change(screen.getByLabelText("Start URL"), {
      target: { value: "https://example.com/docs" },
    });
    fireEvent.change(screen.getByLabelText("Approved domain"), {
      target: { value: "example.com" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Add website" }));
    expect(
      await screen.findByText(/Members receive HTTP 403 from the server/),
    ).toBeInTheDocument();
  });
});

describe("DocumentLibrary delete and pagination", () => {
  it("deletes after confirmation and announces success", async () => {
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
    renderSurface(<DocumentLibrary />);
    fireEvent.click(await screen.findByRole("button", { name: "Document actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(screen.getByRole("heading", { name: "Delete document?" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    await waitFor(() => {
      expect(deleteDocument).toHaveBeenCalledWith(
        expect.objectContaining({ accessToken: "jwt-token" }),
        "doc-1",
      );
    });
    expect(await screen.findByText("Document deleted.")).toBeInTheDocument();
  });

  it("keeps the row and shows 403 copy when the server forbids delete", async () => {
    listDocuments.mockResolvedValue([
      {
        document_id: "doc-1",
        title: "Policy",
        visibility: "company",
        current_version_id: "ver-1",
        visibility_generation: 1,
        created_at: "2026-08-24T00:00:00Z",
      },
    ]);
    deleteDocument.mockRejectedValue(
      new ClassifiedApiError({ kind: "auth", status: 403, detail: "forbidden" }),
    );
    renderSurface(<DocumentLibrary />);
    fireEvent.click(await screen.findByRole("button", { name: "Document actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    expect(await screen.findByText("You cannot delete this document.")).toBeInTheDocument();
    expect(await screen.findAllByText("Policy")).not.toHaveLength(0);
  });

  it("appends the next page without duplicate ids and hides Load more on a short page", async () => {
    const first = Array.from({ length: 50 }, (_, index) => ({
      document_id: `doc-${String(index)}`,
      title: `Doc ${String(index)}`,
      visibility: "company",
      current_version_id: null,
      visibility_generation: 1,
      created_at: "2026-08-24T00:00:00Z",
    }));
    listDocuments.mockImplementation(
      async (
        _auth: unknown,
        options: { cursor?: string | null; limit?: number } = {},
      ) => {
        if (options.cursor) {
          return [
            {
              document_id: "doc-extra",
              title: "Extra",
              visibility: "company",
              current_version_id: null,
              visibility_generation: 1,
              created_at: "2026-08-23T00:00:00Z",
            },
          ];
        }
        return first;
      },
    );
    renderSurface(<DocumentLibrary />);
    expect(await screen.findByText("Doc 0")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /preview/i })).toBeNull();
    expect(screen.queryByText(/Source preview and download are not available/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    expect(await screen.findByText("Extra")).toBeInTheDocument();
    expect(screen.getAllByText(/^Doc /).length + 1).toBeGreaterThan(50);
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
    const cursors = listDocuments.mock.calls.map((call) => call[1]?.cursor);
    expect(cursors).toContain("2026-08-24T00:00:00Z,doc-49");
  });
});

describe("DocumentDetail delete and context links", () => {
  it("navigates home after 204 and seeds graph with the document id", async () => {
    fetchDocument.mockResolvedValue({
      ok: true,
      document: {
        document_id: "doc-1",
        title: "Policy",
        visibility: "company",
        current_version_id: "ver-1",
        visibility_generation: 1,
        created_at: "2026-08-24T00:00:00Z",
      },
    });
    fetchVersionStatus.mockResolvedValue({
      version: {
        version_id: "ver-1",
        document_id: "doc-1",
        status: "hybrid_ready",
        retrieval_eligible: true,
        document_graph_eligible: true,
        hybrid_verified_at: null,
        bm25_verified_at: null,
        graph_handoff_at: null,
        retry_allowed: false,
        bm25: {
          active_index_version: 1,
          index_schema_version: "v1",
          lag_seconds: 0,
          pending: 0,
          processing: 0,
          failed: 0,
          dead_letter: 0,
          retry_attempts: 0,
          verified_at: null,
        },
        graph_handoff: {
          pending: 0,
          processing: 0,
          completed: 1,
          failed: 0,
          dead_letter: 0,
        },
      },
      recent_jobs: [],
    });
    listTables.mockResolvedValue([
      {
        table_id: "t-own",
        document_id: "doc-1",
        version_id: "ver-1",
        table_name: "Owned table",
        sheet_name: "Sheet1",
        row_count: 2,
        column_count: 2,
      },
      {
        table_id: "t-other",
        document_id: "doc-other",
        version_id: "ver-other",
        table_name: "Other table",
        sheet_name: "Sheet2",
        row_count: 1,
        column_count: 1,
      },
    ]);
    renderSurface(<DocumentDetail documentId="doc-1" />);
    expect(await screen.findByRole("link", { name: "Inspect in graph" })).toHaveAttribute(
      "href",
      "/graph?documentId=doc-1",
    );
    expect(screen.getByRole("link", { name: "Open tables" })).toHaveAttribute("href", "/tables");
    expect(screen.getByText("Owned table")).toBeInTheDocument();
    expect(screen.queryByText("Other table")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Document actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/documents?deleted=1");
    });
  });

  it("navigates away on a second 404 without leaking a title", async () => {
    fetchDocument.mockResolvedValue({
      ok: true,
      document: {
        document_id: "doc-1",
        title: "SECRET TITLE",
        visibility: "company",
        current_version_id: null,
        visibility_generation: 1,
        created_at: null,
      },
    });
    deleteDocument.mockRejectedValue(new ClassifiedApiError({ kind: "deleted" }));
    renderSurface(<DocumentDetail documentId="doc-1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Document actions" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete document" }));
    await waitFor(() => {
      expect(routerPush).toHaveBeenCalledWith("/documents");
    });
  });
});
