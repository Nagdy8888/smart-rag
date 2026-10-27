// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CitationSheet } from "./citation-sheet";
import { CitationDrawer } from "./citation-drawer";
import { hrefForCitationRecord } from "../../lib/citation-drawer";
import type { CitationResponse } from "../../lib/types";

const web: CitationResponse = {
  citation_id: "web-c1", citation_index: 1, chunk_id: null,
  source_kind: "web", source_unavailable: false,
  source_url: "https://www.rfc-editor.org/rfc/rfc6585",
  provenance: { title: "RFC 6585: Too-Many-Requests" },
  evidence_excerpt: "The 429 status code indicates too many requests.",
};
afterEach(cleanup);
describe("Web citation reader", () => {
  it("opens the passage reader from the source chip instead of leaving Ask", () => {
    const select = vi.fn();
    render(<CitationSheet open onClose={vi.fn()} citations={[web]}
      hrefForCitation={hrefForCitationRecord} onSelectCitation={select} />);
    fireEvent.click(screen.getByRole("button", { name: /Citation 1/ }));
    expect(select).toHaveBeenCalledWith(web, expect.any(HTMLButtonElement));
    expect(screen.getByText(/Too-Many-Requests/)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
  });
  it("shows the saved supporting passage and a separate safe original-page link", () => {
    render(<CitationDrawer citation={web} onClose={vi.fn()} />);
    expect(screen.getByText(web.evidence_excerpt!)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open web page/ })).toHaveAttribute("href", web.source_url);
    expect(screen.getByRole("link", { name: /Open web page/ })).toHaveAttribute("rel", "noopener noreferrer");
  });
  it.each(["javascript:alert(1)", "data:text/html,unsafe"])("does not link unsafe URLs: %s", (source_url) => {
    render(<CitationDrawer citation={{ ...web, source_url }} onClose={vi.fn()} />);
    expect(screen.queryByRole("link", { name: /Open web page/ })).toBeNull();
  });
  it("does not link an unavailable web source", () => {
    const unavailable = { ...web, source_unavailable: true };
    expect(hrefForCitationRecord(unavailable)).toBeUndefined();
    render(<CitationDrawer citation={unavailable} onClose={vi.fn()} />);
    expect(screen.queryByRole("link", { name: /Open web page/ })).toBeNull();
    expect(screen.queryByText(web.evidence_excerpt!)).toBeNull();
  });
});
