/**
 * Client nav visibility is convenience only and is not HTTP 403.
 */

import { describe, expect, it } from "vitest";
import {
  CLIENT_NAV_IS_NOT_AUTHORIZATION,
  clientControlIsAuthorizationBoundary,
  forgedClientRoleIsAuthorization,
  hiddenNavImpliesForbidden,
} from "./client-authorization";
import { paidMutationHeaders, resumeHeaders } from "./api";

describe("client authorization honesty", () => {
  it("treats omitted AppShell items as not forbidden", () => {
    expect(CLIENT_NAV_IS_NOT_AUTHORIZATION).toBe(true);
    expect(hiddenNavImpliesForbidden("/admin")).toBe(false);
    expect(hiddenNavImpliesForbidden("/tools")).toBe(false);
    expect(clientControlIsAuthorizationBoundary()).toBe(false);
  });

  it("does not treat a forged client role as request authorization", () => {
    expect(forgedClientRoleIsAuthorization()).toBe(false);
    const forgedRole = "owner";
    void forgedRole;
    const headers = paidMutationHeaders({ accessToken: "jwt-token" });
    expect(headers.Authorization).toBe("Bearer jwt-token");
    expect(headers["X-Role"]).toBeUndefined();
    expect(headers["X-Test-Role"]).toBeUndefined();
    expect(Object.keys(headers).some((key) => /role/i.test(key))).toBe(false);
    expect(resumeHeaders({ accessToken: "jwt-token" })["X-Test-Role"]).toBeUndefined();
  });
});
