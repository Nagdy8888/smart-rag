import { describe, expect, it } from "vitest";
import { citationChipHref } from "./citation-drawer";
import { COMPOSER_MAX_CHARS, composerDraftIsSendable } from "./composer";
import { objectNameForUpload } from "./upload-client";

describe("citationChipHref", () => {
  it("never returns a privileged or public href (GAP-07-09)", () => {
    expect(citationChipHref("https://storage.example/secret")).toBeNull();
    expect(citationChipHref("javascript:alert(1)")).toBeNull();
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
