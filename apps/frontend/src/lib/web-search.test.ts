import { describe, expect, it } from "vitest";
import { SEARCH_SCOPE_LABELS, requestedSearchScopeLabel } from "./types/chat";
import {
  visibleRequestedSearchScope,
  visibleSearchScopes,
  webSearchCapability,
} from "./web-search";

describe("SEARCH_SCOPE_LABELS", () => {
  it("uses the exact Ask dropdown labels", () => {
    expect(SEARCH_SCOPE_LABELS).toEqual({
      auto: "Auto",
      company_documents: "Company documents",
      general_knowledge: "General",
      web: "Web",
    });
    expect(requestedSearchScopeLabel("company_documents")).toBe(
      "Company documents",
    );
    expect(requestedSearchScopeLabel("general_knowledge")).toBe("General");
    expect(requestedSearchScopeLabel("web")).toBe("Web");
  });
});

describe("webSearchCapability", () => {
  it("is false until /api/meta explicitly enables Web", () => {
    expect(webSearchCapability(null)).toBe(false);
    expect(webSearchCapability(undefined)).toBe(false);
    expect(webSearchCapability({ web_search_enabled: false })).toBe(false);
    expect(webSearchCapability({ web_search_enabled: true })).toBe(true);
  });
});

describe("visibleSearchScopes", () => {
  it("always lists Web in catalog order", () => {
    expect(visibleSearchScopes(false)).toEqual([
      "auto",
      "company_documents",
      "general_knowledge",
      "web",
    ]);
    expect(visibleSearchScopes(true)).toEqual([
      "auto",
      "company_documents",
      "general_knowledge",
      "web",
    ]);
  });
});

describe("visibleRequestedSearchScope", () => {
  it("keeps stored Web when the server flag is off", () => {
    expect(visibleRequestedSearchScope("web", false)).toBe("web");
    expect(visibleRequestedSearchScope("web", true)).toBe("web");
    expect(visibleRequestedSearchScope("company_documents", false)).toBe(
      "company_documents",
    );
  });
});
