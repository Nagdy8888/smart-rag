import { describe, expect, it } from "vitest";
import { isPublicAuthPath } from "./paths";

describe("public auth paths", () => {
  it("allows Auth-direct routes without treating them as the security boundary", () => {
    expect(isPublicAuthPath("/review-fixtures")).toBe(false);
    expect(isPublicAuthPath("/signup")).toBe(true);
    expect(isPublicAuthPath("/mfa/challenge")).toBe(false);
    expect(isPublicAuthPath("/mfa/enroll")).toBe(false);
    expect(isPublicAuthPath("/unavailable/GAP-07-07")).toBe(false);
    expect(isPublicAuthPath("/fonts/inter-latin-400-normal.woff2")).toBe(true);
    expect(isPublicAuthPath("/")).toBe(false);
    expect(isPublicAuthPath("/invitations/accept")).toBe(false);
  });
});
