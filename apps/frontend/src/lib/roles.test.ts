import { describe, expect, it } from "vitest";
import {
  showAdminMutationConvenience,
  showCompanyUsageConvenience,
  showCrawlConvenience,
  showInviteConvenience,
  showOffboardConvenience,
  showToolEnableConvenience,
  showUploadConvenience,
} from "./roles";

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

  it("hides invite, offboard, and enable for viewer and member", () => {
    for (const role of ["viewer", "member"] as const) {
      expect(showInviteConvenience(role)).toBe(false);
      expect(showOffboardConvenience(role)).toBe(false);
      expect(showToolEnableConvenience(role)).toBe(false);
      expect(showAdminMutationConvenience(role)).toBe(false);
      expect(showCompanyUsageConvenience(role)).toBe(false);
    }
    expect(showInviteConvenience("owner")).toBe(true);
    expect(showOffboardConvenience("admin")).toBe(true);
    expect(showToolEnableConvenience("owner")).toBe(true);
  });
});
