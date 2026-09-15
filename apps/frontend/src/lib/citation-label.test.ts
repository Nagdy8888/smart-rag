import { describe, expect, it } from "vitest";
import {
  citationChipName,
  citationDisplayPage,
  citationLocatorFields,
  citationSourceLabel,
} from "./citation-label";
import type { CitationResponse } from "./types";

function citation(
  overrides: Partial<CitationResponse> = {},
): CitationResponse {
  return {
    citation_id: "cite-1",
    citation_index: 0,
    chunk_id: "chunk-1",
    provenance: {},
    source_unavailable: false,
    ...overrides,
  };
}

describe("citationSourceLabel", () => {
  it("uses page, title, and heading instead of UUIDs", () => {
    expect(
      citationSourceLabel(
        citation({
          provenance: {
            document_title: "Building applications with AI agents",
            page_number: 129,
            section_path: ["Chapter 6", "Parallel Tool Execution"],
          },
        }),
      ),
    ).toBe(
      "Building applications with AI agents · p. 129 · Parallel Tool Execution",
    );
    expect(
      citationChipName(
        citation({
          citation_index: 1,
          provenance: { page_number: 3 },
        }),
      ),
    ).toBe("Citation 1, p. 3");
  });

  it("prefers the printed page label over the file index", () => {
    expect(
      citationSourceLabel(
        citation({
          provenance: {
            document_title: "AI agents",
            page_number: 201,
            page_label: "179",
          },
        }),
      ),
    ).toBe("AI agents · p. 179");
    expect(citationDisplayPage({ page_number: 201, page_label: "179" })).toBe(
      "179",
    );
  });

  it("falls back to Evidence instead of a citation UUID", () => {
    expect(citationSourceLabel(citation())).toBe("Evidence");
    expect(citationChipName(citation({ citation_index: 2 }))).toBe("Citation 2");
  });

  it("labels unavailable sources without leaking stored titles", () => {
    expect(
      citationSourceLabel(
        citation({
          source_unavailable: true,
          provenance: { document_title: "SECRET TITLE", page_number: 7 },
        }),
      ),
    ).toBe("Source unavailable");
  });
});

describe("citationLocatorFields", () => {
  it("lists locators then technical ids", () => {
    const fields = citationLocatorFields(
      citation({
        provenance: {
          document_title: "Policy",
          page_number: 12,
          section_path: ["Refunds"],
        },
      }),
    );
    expect(fields.locators).toEqual([
      { key: "document_title", label: "Document", value: "Policy" },
      { key: "page_number", label: "PDF page", value: "12" },
      { key: "section_path", label: "Section", value: "Refunds" },
    ]);
    expect(fields.technical.map((item) => item.key)).toEqual([
      "citation_id",
      "chunk_id",
    ]);
  });

  it("shows printed page and PDF page when they differ", () => {
    const fields = citationLocatorFields(
      citation({
        provenance: {
          document_title: "AI agents",
          page_number: 201,
          page_label: "179",
        },
      }),
    );
    expect(fields.locators).toEqual([
      { key: "document_title", label: "Document", value: "AI agents" },
      { key: "page_label", label: "Page", value: "179" },
      { key: "page_number", label: "PDF page", value: "201" },
    ]);
  });

  it("labels web citations with title and URL, never a company document title", () => {
    expect(
      citationSourceLabel(
        citation({
          source_kind: "web",
          chunk_id: null,
          provenance: {
            title: "Example briefing",
            url: "https://example.test/brief",
          },
        }),
      ),
    ).toBe("Example briefing");
    expect(
      citationLocatorFields(
        citation({
          source_kind: "web",
          chunk_id: null,
          provenance: {
            title: "Example briefing",
            url: "https://example.test/brief",
          },
        }),
      ).locators,
    ).toEqual([
      { key: "title", label: "Title", value: "Example briefing" },
      { key: "url", label: "URL", value: "https://example.test/brief" },
    ]);
  });
});
