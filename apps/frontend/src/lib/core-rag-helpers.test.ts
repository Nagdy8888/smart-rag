import { describe, expect, it } from "vitest";
import { citationChipHref, hrefForCitationRecord } from "./citation-drawer";
import { COMPOSER_MAX_CHARS, composerDraftIsSendable } from "./composer";
import { objectNameForUpload } from "./upload-client";

describe("citationChipHref", () => {
  it("never returns a privileged or public href for company citations (GAP-07-09)", () => {
    expect(citationChipHref("https://storage.example/secret")).toBeNull();
    expect(
      citationChipHref("https://example.test/doc", "company_document"),
    ).toBeNull();
    expect(citationChipHref("javascript:alert(1)")).toBeNull();
  });

  it("returns a safe http(s) href only for web citations", () => {
    expect(citationChipHref("https://example.test/page", "web")).toBe(
      "https://example.test/page",
    );
    expect(citationChipHref("http://example.test/page", "web")).toBe(
      "http://example.test/page",
    );
    expect(citationChipHref("javascript:alert(1)", "web")).toBeNull();
    expect(citationChipHref("/relative", "web")).toBeNull();
  });

  it("never turns a company citation into an href even with https provenance", () => {
    expect(
      hrefForCitationRecord({
        citation_id: "c1",
        citation_index: 1,
        chunk_id: "ch1",
        provenance: { url: "https://storage.example/secret" },
        source_unavailable: false,
        source_kind: "company_document",
      }),
    ).toBeUndefined();
    expect(
      hrefForCitationRecord({
        citation_id: "c2",
        citation_index: 1,
        chunk_id: null,
        provenance: { url: "https://example.test/page" },
        source_unavailable: false,
        source_kind: "web",
      }),
    ).toBe("https://example.test/page");
  });
});

describe("composer", () => {
  it("caps at 16384 and disables empty drafts", () => {
    expect(COMPOSER_MAX_CHARS).toBe(16384);
    expect(composerDraftIsSendable("")).toBe(false);
    expect(composerDraftIsSendable("  hi  ")).toBe(true);
    expect(composerDraftIsSendable("x".repeat(16385))).toBe(false);
  });
});

describe("objectNameForUpload", () => {
  it("uses the reservation prefix and strips path traversal", () => {
    expect(objectNameForUpload("user/res/", "../x.pdf")).toBe("user/res/x.pdf");
    expect(objectNameForUpload("user/res", "<img src=x onerror=alert(1)>.pdf")).toContain(
      "user/res/",
    );
  });
});

describe("GAP-07-14 removal", () => {
  it("does not keep document-delete-unavailable copy", async () => {
    const drawer = await import("./citation-drawer");
    expect("DOCUMENT_DELETE_UNAVAILABLE" in drawer).toBe(false);
  });
});
