// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactElement } from "react";
import "@testing-library/jest-dom/vitest";
import { activateCanvasNode } from "./graph-canvas";
import { GraphExplorer } from "./graph-explorer";
import { SessionProvider } from "../../lib/auth/session-provider";
import { ClassifiedApiError } from "../../lib/api";
import {
  EMPTY_INSPECT_COPY,
  GRAPH_ENTITY_LIMIT_COPY,
  GRAPH_INSPECT_BOUNDS_COPY,
} from "../../lib/graph-client";
import { MIXED_BIDI, XSS_ENTITY } from "../../lib/hostile-text-fixtures";
import { limitationCopy } from "../../lib/limitations";

const fetchMe = vi.fn();
const fetchMeta = vi.fn();
const searchGraphEntities = vi.fn();
const inspectGraph = vi.fn();

const { navState } = vi.hoisted(() => ({
  navState: { search: new URLSearchParams() },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/graph",
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
    searchGraphEntities: (...args: unknown[]) => searchGraphEntities(...args),
    inspectGraph: (...args: unknown[]) => inspectGraph(...args),
  };
});

const HIT = {
  object_id: "acme",
  object_type: "entity",
  chunk_id: "c1",
  document_id: "d1",
  version_id: "v1",
  support: 1,
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
  searchGraphEntities.mockReset();
  searchGraphEntities.mockResolvedValue([HIT]);
  inspectGraph.mockReset();
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
    locators: [
      {
        chunk_id: "c1",
        document_id: "d1",
        version_id: "v1",
        page_number: 3,
        section_path: ["Intro"],
        sheet_name: null,
        range_ref: null,
        source_url: null,
      },
    ],
    limitations: [],
    row_count: 1,
    depth: 3,
  });
});

/**
 * Wrap Graph with Query + session.
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
 * Search, select the fixture hit, and inspect.
 */
async function searchSelectInspect(): Promise<void> {
  fireEvent.change(await screen.findByLabelText("Search entities"), {
    target: { value: "acme" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  fireEvent.click(await screen.findByRole("button", { name: /acme/i }));
  fireEvent.click(screen.getByRole("button", { name: "Inspect graph" }));
}

describe("GraphExplorer", () => {
  it("searches, inspects, lists nodes, and opens evidence details", async () => {
    renderSurface(<GraphExplorer />);
    await searchSelectInspect();
    expect(await screen.findByText("hop 1")).toBeInTheDocument();
    expect(inspectGraph).toHaveBeenCalledTimes(1);
    const body = inspectGraph.mock.calls[0]?.[1] as { entity_keys: string[]; depth: number };
    expect(body.entity_keys).toEqual(["acme"]);
    expect(body.depth).toBe(3);
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.getAllByText("Evidence details").length).toBeGreaterThan(0);
    expect(screen.getByText("Intro")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add relationship" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Export" })).toBeNull();
    expect(screen.queryByRole("img", { name: "Bounded graph neighborhood" })).toBeNull();
    expect(document.querySelector("svg[aria-label='Bounded graph neighborhood']")).toBeNull();
  });

  it("inspects from a document seed without entity chips", async () => {
    navState.search = new URLSearchParams("documentId=11111111-1111-4111-8111-111111111111");
    renderSurface(<GraphExplorer />);
    const inspect = await screen.findByRole("button", { name: "Inspect graph" });
    await waitFor(() => expect(inspect).toBeEnabled());
    fireEvent.click(inspect);
    await screen.findByText("hop 1");
    const body = inspectGraph.mock.calls[0]?.[1] as { document_id: string; entity_keys: string[] };
    expect(body.document_id).toBe("11111111-1111-4111-8111-111111111111");
    expect(body.entity_keys).toEqual([]);
  });

  it("keeps list as default and toggles canvas without a second SVG", async () => {
    renderSurface(<GraphExplorer />);
    await searchSelectInspect();
    expect(await screen.findByRole("button", { name: "List" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    fireEvent.click(screen.getByRole("button", { name: "Canvas" }));
    expect(screen.getByRole("button", { name: "Canvas" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByRole("img", { name: "Bounded graph neighborhood" })).toBeNull();
  });

  it("labels canvas as supplementary and returns to the accessible list", async () => {
    renderSurface(<GraphExplorer />);
    await searchSelectInspect();
    fireEvent.click(screen.getByRole("button", { name: "Canvas" }));
    expect(
      await screen.findByLabelText("Supplementary graph canvas"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open accessible list" }));
    expect(screen.getByRole("button", { name: "List" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByTestId("graph-accessible-list")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.getAllByText("Evidence details").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("shows empty inspect copy and truthful bounds", async () => {
    inspectGraph.mockResolvedValue({
      nodes: [],
      locators: [],
      limitations: [],
      row_count: 0,
      depth: 3,
    });
    renderSurface(<GraphExplorer />);
    await searchSelectInspect();
    expect(await screen.findByText(EMPTY_INSPECT_COPY)).toBeInTheDocument();
    expect(screen.getByText(GRAPH_INSPECT_BOUNDS_COPY, { exact: false })).toBeInTheDocument();
  });

  it("caps chips at 12 and shows mixed-direction labels as text", async () => {
    const hits = [
      { ...HIT, object_id: MIXED_BIDI, chunk_id: "c-mix" },
      ...Array.from({ length: 11 }, (_, index) => ({
        ...HIT,
        object_id: `ent-${String(index)}`,
        chunk_id: `c-${String(index)}`,
      })),
    ];
    searchGraphEntities.mockResolvedValue(hits);
    renderSurface(<GraphExplorer />);
    fireEvent.change(await screen.findByLabelText("Search entities"), {
      target: { value: "ent" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText(MIXED_BIDI);
    const searchRegion = screen.getByRole("region", { name: "Entity search" });
    const hitButtons = within(searchRegion)
      .getAllByRole("button")
      .filter((button) => button.getAttribute("type") === "button");
    expect(hitButtons).toHaveLength(12);
    for (const hit of hitButtons) {
      fireEvent.click(hit);
    }
    expect(screen.getByText(GRAPH_ENTITY_LIMIT_COPY)).toBeInTheDocument();
    expect(screen.getAllByText(MIXED_BIDI).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: `Remove ${MIXED_BIDI}` }));
    expect(screen.queryByText(GRAPH_ENTITY_LIMIT_COPY)).toBeNull();
  });

  it("distinguishes graph outage from ACL blindness", async () => {
    inspectGraph.mockResolvedValue({
      nodes: [],
      locators: [],
      limitations: [{ code: "graph_outage", count: 4 }],
      row_count: 0,
      depth: 3,
    });
    renderSurface(<GraphExplorer />);
    await searchSelectInspect();
    expect(await screen.findByText(limitationCopy("graph_outage"), { exact: false })).toBeInTheDocument();
    expect(screen.queryByText("4")).toBeNull();
    expect(screen.queryByText(/relationship editing/i)).toBeNull();
  });

  it("preserves chips on inspect 403", async () => {
    inspectGraph.mockRejectedValue(
      new ClassifiedApiError({
        kind: "auth",
        status: 403,
        detail: "forbidden",
      }),
    );
    renderSurface(<GraphExplorer />);
    await searchSelectInspect();
    expect(await screen.findByText(/Server denied this request/)).toBeInTheDocument();
    expect(screen.getByLabelText("Selected entities")).toHaveTextContent("acme");
  });

  it("maps focused canvas Enter and Space to the same onSelect as pointer", () => {
    const onSelect = vi.fn();
    const node = {
      object_id: XSS_ENTITY,
      object_type: "entity",
      chunk_id: "c1",
      document_id: "d1",
      version_id: "v1",
      support: 1,
      hop: 1,
    };
    const preventDefault = vi.fn();
    activateCanvasNode(
      { key: "Enter", preventDefault } as unknown as KeyboardEvent,
      onSelect,
      node,
    );
    activateCanvasNode(
      { key: " ", preventDefault } as unknown as KeyboardEvent,
      onSelect,
      node,
    );
    expect(onSelect).toHaveBeenCalledTimes(2);
    expect(onSelect).toHaveBeenNthCalledWith(1, node);
    expect(onSelect).toHaveBeenNthCalledWith(2, node);
    expect(preventDefault).toHaveBeenCalledTimes(2);
  });

  it("does not search for an empty query", async () => {
    renderSurface(<GraphExplorer />);
    expect(await screen.findByRole("button", { name: "Search" })).toBeDisabled();
    expect(searchGraphEntities).not.toHaveBeenCalled();
  });
});
