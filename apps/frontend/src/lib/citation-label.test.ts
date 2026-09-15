import { describe, expect, it } from "vitest";
import {
  citationChipName,
  citationDisplayPage,
  citationDrawerTitle,
  citationLocatorFields,
  citationSourceLabel,
  citationsForParagraph,
  splitVerifiedParagraphs,
  unmappedCitations,
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
  it("labels company PDFs from typed title and viewer page", () => {
    expect(
      citationSourceLabel(
        citation({
          document_title: "Building applications with AI agents",
          pdf_page_number: 129,
          provenance: {
            document_title: "Building applications with AI agents",
            page_number: 12,
            page_label: "12",
            section_path: ["Chapter 6", "Parallel Tool Execution"],
          },
        }),
      ),
    ).toBe("Building applications with AI agents · PDF page 129");
    expect(
      citationChipName(
        citation({
          citation_index: 1,
          pdf_page_number: 3,
        }),
      ),
    ).toBe("Citation 1, Source · PDF page 3");
  });

  it("does not use printed page_label for a company PDF chip", () => {
    expect(
      citationSourceLabel(
        citation({
          document_title: "AI agents",
          pdf_page_number: 25,
          provenance: {
            document_title: "AI agents",
            page_number: 201,
            page_label: "12",
          },
        }),
      ),
    ).toBe("AI agents · PDF page 25");
    expect(citationDisplayPage({ page_number: 201, page_label: "179" })).toBe(
      "179",
    );
    expect(
      citationSourceLabel(
        citation({
          document_title: "AI agents",
          pdf_page_number: 25,
          provenance: { page_label: "12" },
        }),
      ),
    ).not.toContain("12");
  });

  it("uses Source and unavailable when typed PDF fields are missing", () => {
    expect(citationSourceLabel(citation())).toBe(
      "Source · PDF page unavailable",
    );
    expect(citationChipName(citation({ citation_index: 2 }))).toBe(
      "Citation 2, Source · PDF page unavailable",
    );
  });

  it("labels unavailable sources without leaking stored titles", () => {
    expect(
      citationSourceLabel(
        citation({
          source_unavailable: true,
          document_title: "SECRET TITLE",
          pdf_page_number: 7,
          provenance: { document_title: "SECRET TITLE", page_number: 7 },
        }),
      ),
    ).toBe("Source unavailable");
  });

  it("keeps sheet locators on the previous format", () => {
    expect(
      citationSourceLabel(
        citation({
          source_kind: "company_document",
          provenance: {
            document_title: "Budget",
            sheet_name: "Q1",
            range_ref: "A1:B2",
          },
        }),
      ),
    ).toBe("Budget · Q1 A1:B2");
  });
});

describe("citationLocatorFields", () => {
  it("lists book title and typed PDF page for company PDFs", () => {
    const fields = citationLocatorFields(
      citation({
        document_title: "Policy",
        pdf_page_number: 12,
        provenance: {
          document_title: "Policy",
          page_number: 99,
          page_label: "xii",
          section_path: ["Refunds"],
        },
      }),
    );
    expect(fields.locators).toEqual([
      { key: "document_title", label: "Book/source", value: "Policy" },
      { key: "pdf_page_number", label: "PDF page", value: "12" },
      { key: "section_path", label: "Section", value: "Refunds" },
    ]);
    expect(fields.technical.map((item) => item.key)).toEqual([
      "citation_id",
      "chunk_id",
    ]);
  });

  it("omits printed page_label from company PDF locators", () => {
    const fields = citationLocatorFields(
      citation({
        document_title: "AI agents",
        pdf_page_number: 201,
        provenance: {
          document_title: "AI agents",
          page_number: 201,
          page_label: "179",
        },
      }),
    );
    expect(fields.locators).toEqual([
      { key: "document_title", label: "Book/source", value: "AI agents" },
      { key: "pdf_page_number", label: "PDF page", value: "201" },
    ]);
    expect(fields.locators.some((item) => item.key === "page_label")).toBe(
      false,
    );
  });

  it("omits stale locators when the source is unavailable", () => {
    const fields = citationLocatorFields(
      citation({
        source_unavailable: true,
        document_title: "SECRET TITLE",
        pdf_page_number: 7,
      }),
    );
    expect(fields.locators).toEqual([]);
  });
});

describe("citationDrawerTitle", () => {
  it("uses book title and typed PDF page", () => {
    expect(
      citationDrawerTitle(
        citation({
          document_title: "AI Agents",
          pdf_page_number: 25,
          provenance: { page_label: "12" },
        }),
      ),
    ).toBe("AI Agents — PDF page 25");
  });
});

describe("splitVerifiedParagraphs", () => {
  it("splits on blank lines without trimming", () => {
    expect(splitVerifiedParagraphs("One.\n\nTwo.")).toEqual(["One.", "Two."]);
    expect(splitVerifiedParagraphs("")).toEqual([]);
  });
});

describe("paragraph citation grouping", () => {
  it("keeps null-index rows out of mapped paragraphs", () => {
    const mapped = citation({ citation_id: "m", paragraph_index: 0 });
    const legacy = citation({ citation_id: "l", paragraph_index: null });
    expect(citationsForParagraph([mapped, legacy], 0)).toEqual([mapped]);
    expect(unmappedCitations([mapped, legacy], 1)).toEqual([legacy]);
  });
});
