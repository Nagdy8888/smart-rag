/**
 * Client nav visibility is convenience only and is not HTTP 403.
 */

import { describe, expect, it } from "vitest";
import {
  CLIENT_NAV_IS_NOT_AUTHORIZATION,
  clientControlIsAuthorizationBoundary,
  hiddenNavImpliesForbidden,
} from "./client-authorization";

describe("client authorization honesty", () => {
  it("treats omitted AppShell items as not forbidden", () => {
    expect(CLIENT_NAV_IS_NOT_AUTHORIZATION).toBe(true);
    expect(hiddenNavImpliesForbidden("/admin")).toBe(false);
    expect(hiddenNavImpliesForbidden("/tools")).toBe(false);
    expect(clientControlIsAuthorizationBoundary()).toBe(false);
  });
});
