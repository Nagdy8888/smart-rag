import { describe, expect, it } from "vitest";
import {
  decodeHtmlEscapeEntities,
  displayText,
  formatProvenance,
  isSafeHttpUrl,
} from "./safe-text";

describe("displayText", () => {
  it("strips NUL bytes from XSS payloads", () => {
    expect(displayText("alert\u0000(1)")).toBe("alert(1)");
  });

  it("returns empty for non-strings", () => {
    expect(displayText({ html: "<img>" })).toBe("");
  });

  it("shows API-escaped quotes as real quotation marks", () => {
    expect(
      displayText("&quot;Hello from the other side&quot; is a lyric"),
    ).toBe('"Hello from the other side" is a lyric');
  });
});

describe("decodeHtmlEscapeEntities", () => {
  it("inverts Python html.escape quote=True output", () => {
    expect(decodeHtmlEscapeEntities("&lt;script&gt;")).toBe("<script>");
    expect(decodeHtmlEscapeEntities("it&#x27;s")).toBe("it's");
    expect(decodeHtmlEscapeEntities("&amp;quot;")).toBe("&quot;");
  });
});

describe("isSafeHttpUrl", () => {
  it("rejects javascript and data URLs", () => {
    expect(isSafeHttpUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeHttpUrl("data:text/html,<script>")).toBe(false);
  });

  it("allows http and https", () => {
    expect(isSafeHttpUrl("https://example.invalid/doc")).toBe(true);
    expect(isSafeHttpUrl("http://127.0.0.1:8000/x")).toBe(true);
  });
});

describe("formatProvenance", () => {
  it("renders coordinates as text without HTML", () => {
    const text = formatProvenance({
      document_title: "Policy",
      page: 3,
      section: "<script>x</script>",
    });
    expect(text).toContain("document_title=Policy");
    expect(text).toContain("page=3");
    expect(text).toContain("section=<script>x</script>");
  });
});
