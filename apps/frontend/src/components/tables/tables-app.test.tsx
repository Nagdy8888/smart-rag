// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { TablesApp } from "./tables-app";
import { SessionProvider } from "../../lib/auth/session-provider";
import { ClassifiedApiError } from "../../lib/api";
import { FORBIDDEN_MUTATION_COPY } from "../../lib/admin-copy";
import { GENERIC_PRODUCTION_ERROR } from "../../lib/failure-copy";
import {
  EMPTY_ANALYZE_ROWS_COPY,
  EMPTY_DOCUMENT_TABLES_COPY,
  EMPTY_MANIFESTS_COPY,
  SQL_REJECTED_COPY,
  UNKNOWN_COLUMN_COPY,
} from "../../lib/table-plan";
import { MIXED_BIDI, XSS_ENTITY, XSS_FILENAME } from "../../lib/hostile-text-fixtures";

const fetchMe = vi.fn();
const fetchMeta = vi.fn();
const listTables = vi.fn();
const analyzeTable = vi.fn();
const fetchDocument = vi.fn();

const { navState } = vi.hoisted(() => ({
  navState: { search: new URLSearchParams() },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/tables",
  useSearchParams: () => navState.search,
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
  }),
}));

vi.mock("../../lib/env", () => ({
  publicSupabaseConfig: () => ({
    url: "http://127.0.0.1:54321",
    anonKey: "anon",
  }),
  apiBaseUrl: () => "http://127.0.0.1:8000",
}));

vi.mock("../../lib/api", async () => {
  const actual = await vi.importActual<typeof import("../../lib/api")>("../../lib/api");
  return {
    ...actual,
    fetchMe: (...args: unknown[]) => fetchMe(...args),
    fetchMeta: (...args: unknown[]) => fetchMeta(...args),
    listTables: (...args: unknown[]) => listTables(...args),
    analyzeTable: (...args: unknown[]) => analyzeTable(...args),
    fetchDocument: (...args: unknown[]) => fetchDocument(...args),
  };
});

const MANIFEST = {
  table_id: "11111111-1111-4111-8111-111111111111",
  document_id: "d1",
  version_id: "22222222-2222-4222-8222-222222222222",
  table_name: XSS_FILENAME,
  sheet_name: "Sheet1",
  row_count: 2,
  column_count: 2,
};

afterEach(() => {
  cleanup();
});

beforeEach(() => {
  navState.search = new URLSearchParams();
  fetchMeta.mockResolvedValue({
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  });
  fetchMe.mockResolvedValue({
    user_id: "u1",
    role: "member",
    authorization_version: 1,
    upload_enabled: true,
  });
  listTables.mockResolvedValue([MANIFEST]);
  fetchDocument.mockResolvedValue({
    ok: true,
    document: {
      document_id: MANIFEST.document_id,
      title: "Policy handbook",
      visibility: "company",
      current_version_id: MANIFEST.version_id,
      visibility_generation: 1,
      created_at: "2026-08-24T00:00:00Z",
    },
  });
  analyzeTable.mockReset();
  analyzeTable.mockResolvedValue({
    table_id: MANIFEST.table_id,
    version_id: MANIFEST.version_id,
    document_id: MANIFEST.document_id,
    rows: [{ amount: 1 }, { amount: 2 }],
    source_ranges: ["Sheet1!A1:B2"],
  });
});

/**
 * Wrap Tables with Query + session.
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

/**
 * Select the fixture table, add a filter, and submit Analyze.
 */
async function analyzeWithAmountFilter(): Promise<void> {
  fireEvent.click(await screen.findByRole("button", { name: /Sheet1/ }));
  fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
  fireEvent.change(screen.getByLabelText("Filter column"), {
    target: { value: "amount" },
  });
  fireEvent.change(screen.getByLabelText("Filter value"), {
    target: { value: "1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
}

describe("TablesApp", () => {
  it("preselects an accessible tableId from the URL", async () => {
    navState.search = new URLSearchParams(`tableId=${MANIFEST.table_id}`);
    renderSurface(<TablesApp />);
    expect(await screen.findByRole("button", { name: /Sheet1/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("does not preselect an inaccessible tableId even when documentId matches", async () => {
    navState.search = new URLSearchParams(
      `tableId=99999999-9999-4999-8999-999999999999&documentId=${MANIFEST.document_id}`,
    );
    renderSurface(<TablesApp />);
    expect(await screen.findByRole("button", { name: /Sheet1/ })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("runs a valid analyze, labels display sort, and opens cell provenance", async () => {
    renderSurface(<TablesApp />);
    await analyzeWithAmountFilter();
    expect(await screen.findByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(analyzeTable).toHaveBeenCalledTimes(1);
    const posted = analyzeTable.mock.calls[0]?.[1] as { predicates?: unknown };
    expect(posted.predicates).toEqual([
      { column: "amount", operator: "eq", value: 1 },
    ]);
    expect(screen.getByLabelText(/Display sort/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View provenance" }));
    expect(screen.getByRole("heading", { name: "Cell provenance" })).toBeInTheDocument();
    expect(screen.getByText("Sheet1!A1:B2")).toBeInTheDocument();
    expect(
      screen.getAllByRole("link", { name: "Policy handbook" }).some(
        (link) => link.getAttribute("href") === `/documents/${MANIFEST.document_id}`,
      ),
    ).toBe(true);
    expect(screen.queryByRole("link", { name: /source/i })).toBeNull();
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Share" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: /sql/i })).toBeNull();
    expect(screen.getAllByText(XSS_FILENAME, { exact: false }).length).toBeGreaterThan(0);
    expect(document.querySelector("img")).toBeNull();
  });

  it("rejects unknown columns and raw SQL before submission", async () => {
    renderSurface(<TablesApp />);
    fireEvent.click(await screen.findByRole("button", { name: /Sheet1/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
    fireEvent.change(screen.getByLabelText("Filter column"), {
      target: { value: "1amount" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(UNKNOWN_COLUMN_COPY)).toBeInTheDocument();
    expect(analyzeTable).not.toHaveBeenCalled();

    fireEvent.change(screen.getByLabelText("Filter column"), {
      target: { value: "amount" },
    });
    fireEvent.change(screen.getByLabelText("Filter value"), {
      target: { value: "select 1 from t" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(SQL_REJECTED_COPY)).toBeInTheDocument();
    expect(analyzeTable).not.toHaveBeenCalled();
  });

  it("preserves the draft and submitted plan on 403", async () => {
    analyzeTable.mockRejectedValue(
      new ClassifiedApiError({
        kind: "auth",
        status: 403,
        detail: "forbidden",
      }),
    );
    renderSurface(<TablesApp />);
    await analyzeWithAmountFilter();
    expect(await screen.findByText(FORBIDDEN_MUTATION_COPY)).toBeInTheDocument();
    expect(screen.getByLabelText("Filter column")).toHaveValue("amount");
    expect(screen.getByLabelText("Filter value")).toHaveValue("1");
    expect(screen.queryByRole("heading", { name: "Results" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Submitted plan" })).toBeNull();
  });

  it("preserves the plan on 422, 429, and server failure", async () => {
    analyzeTable.mockRejectedValueOnce(
      new ClassifiedApiError({ kind: "validation", detail: "table_plan_rejected" }),
    );
    renderSurface(<TablesApp />);
    await analyzeWithAmountFilter();
    expect(await screen.findByText(/Request invalid/)).toBeInTheDocument();
    expect(screen.getByLabelText("Filter value")).toHaveValue("1");

    analyzeTable.mockRejectedValueOnce(
      new ClassifiedApiError({
        kind: "rate",
        detail: "rate_limited",
        retryAfter: "2",
      }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(/Request limited/)).toBeInTheDocument();

    analyzeTable.mockRejectedValueOnce(new Error("boom"));
    fireEvent.click(screen.getByRole("button", { name: "Analyze" }));
    expect(await screen.findByText(GENERIC_PRODUCTION_ERROR)).toBeInTheDocument();
    expect(screen.getByLabelText("Filter column")).toHaveValue("amount");
  });

  it("shows empty successful rows and omits non-identifier result columns", async () => {
    analyzeTable.mockResolvedValueOnce({
      table_id: MANIFEST.table_id,
      version_id: MANIFEST.version_id,
      document_id: MANIFEST.document_id,
      rows: [],
      source_ranges: [],
    });
    renderSurface(<TablesApp />);
    await analyzeWithAmountFilter();
    expect(await screen.findByText(EMPTY_ANALYZE_ROWS_COPY)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View provenance" })).toBeNull();
  });

  it("renders mixed-direction cells as text and keeps overflow on the table wrap", async () => {
    analyzeTable.mockResolvedValue({
      table_id: MANIFEST.table_id,
      version_id: MANIFEST.version_id,
      document_id: MANIFEST.document_id,
      rows: [{ note: MIXED_BIDI, label: XSS_ENTITY }],
      source_ranges: [],
    });
    renderSurface(<TablesApp />);
    await analyzeWithAmountFilter();
    expect(await screen.findByText(MIXED_BIDI)).toBeInTheDocument();
    expect(screen.getByText(XSS_ENTITY)).toBeInTheDocument();
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByRole("table")).toBeInTheDocument();
  });

  it("shows the empty manifests copy without Export", async () => {
    listTables.mockResolvedValue([]);
    renderSurface(<TablesApp />);
    expect((await screen.findAllByText(EMPTY_MANIFESTS_COPY)).length).toBeGreaterThan(0);
    expect(screen.queryByText("Pick a table to analyze")).toBeNull();
    expect(
      screen.getByText("Run bounded calculations on structured data with exact cell provenance."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeDisabled();
  });

  it("fails closed when listing tables is forbidden", async () => {
    listTables.mockRejectedValue(
      new ClassifiedApiError({
        kind: "auth",
        status: 403,
        detail: "forbidden",
      }),
    );
    renderSurface(<TablesApp />);
    expect(await screen.findByText(FORBIDDEN_MUTATION_COPY)).toBeInTheDocument();
    expect(screen.queryByText(EMPTY_MANIFESTS_COPY)).toBeNull();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it("keeps the submitted plan when display sort changes", async () => {
    renderSurface(<TablesApp />);
    await analyzeWithAmountFilter();
    await screen.findByRole("heading", { name: "Results" });
    fireEvent.change(screen.getByLabelText(/Display sort/), {
      target: { value: "amount" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Toggle display sort direction" }));
    expect(screen.getByRole("heading", { name: "Results" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Submitted plan" })).toBeNull();
  });

  it("names the source document and links through to it", async () => {
    renderSurface(<TablesApp />);
    expect(
      await screen.findByRole("link", { name: "Policy handbook" }),
    ).toHaveAttribute("href", `/documents/${MANIFEST.document_id}`);
  });

  it("scopes the workspace to a document seed and links back", async () => {
    navState.search = new URLSearchParams(`documentId=${MANIFEST.document_id}`);
    renderSurface(<TablesApp />);
    expect(await screen.findByRole("link", { name: "Back to document" })).toHaveAttribute(
      "href",
      `/documents/${MANIFEST.document_id}`,
    );
    expect(screen.getByRole("link", { name: "All tables" })).toHaveAttribute(
      "href",
      "/tables",
    );
    expect(screen.getByRole("heading", { name: "Tables in this document" })).toBeInTheDocument();
    expect((await screen.findAllByText("Policy handbook")).length).toBeGreaterThan(0);
    expect(
      screen.getAllByRole("link", { name: "Policy handbook" })[0],
    ).toHaveAttribute("href", `/documents/${MANIFEST.document_id}`);
    expect(await screen.findByRole("button", { name: /Sheet1/ })).toHaveAttribute(
      "aria-current",
      "true",
    );
  });

  it("hides other documents' tables when the URL seeds a document", async () => {
    listTables.mockResolvedValue([
      MANIFEST,
      {
        ...MANIFEST,
        table_id: "33333333-3333-4333-8333-333333333333",
        document_id: "d2",
        table_name: "Other workbook",
        sheet_name: "OtherSheet",
      },
    ]);
    navState.search = new URLSearchParams(`documentId=${MANIFEST.document_id}`);
    renderSurface(<TablesApp />);
    expect(await screen.findByRole("button", { name: /Sheet1/ })).toBeInTheDocument();
    expect(screen.queryByText("Other workbook")).toBeNull();
  });

  it("explains when the seeded document has no extracted tables", async () => {
    navState.search = new URLSearchParams(`documentId=${MANIFEST.document_id}`);
    listTables.mockResolvedValue([]);
    renderSurface(<TablesApp />);
    expect(await screen.findByRole("link", { name: "Back to document" })).toHaveAttribute(
      "href",
      `/documents/${MANIFEST.document_id}`,
    );
    expect((await screen.findAllByText(EMPTY_MANIFESTS_COPY)).length).toBeGreaterThan(
      0,
    );
    expect(screen.queryByText(EMPTY_DOCUMENT_TABLES_COPY)).toBeNull();
    expect(screen.queryByText("Pick a table to analyze")).toBeNull();
    expect(screen.getByRole("button", { name: "Analyze" })).toBeDisabled();
  });
});
