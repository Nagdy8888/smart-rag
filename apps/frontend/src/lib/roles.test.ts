import { describe, expect, it } from "vitest";
import { showCrawlConvenience, showUploadConvenience } from "./roles";

describe("role convenience hiding", () => {
  it("hides crawl for members and viewers; server remains authoritative", () => {
    expect(showCrawlConvenience("owner")).toBe(true);
    expect(showCrawlConvenience("admin")).toBe(true);
    expect(showCrawlConvenience("member")).toBe(false);
    expect(showCrawlConvenience("viewer")).toBe(false);
  });

  it("hides upload for viewers even when upload_enabled is true", () => {
    expect(showUploadConvenience("viewer", true)).toBe(false);
    expect(showUploadConvenience("member", true)).toBe(true);
    expect(showUploadConvenience("member", false)).toBe(false);
  });
});
