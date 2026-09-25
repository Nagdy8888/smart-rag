import { describe, expect, it } from "vitest";
import { hasPublicSupabaseConfig, isPublicAuthPath } from "./paths";

describe("public auth paths", () => {
  it("allows Auth-direct routes without treating them as the security boundary", () => {
    expect(isPublicAuthPath("/review-fixtures")).toBe(false);
    expect(isPublicAuthPath("/signup")).toBe(true);
    expect(isPublicAuthPath("/mfa/challenge")).toBe(false);
    expect(isPublicAuthPath("/mfa/enroll")).toBe(false);
    expect(isPublicAuthPath("/unavailable/GAP-07-07")).toBe(false);
    expect(isPublicAuthPath("/fonts/ibm-plex-sans-latin-400-normal.woff2")).toBe(true);
    expect(isPublicAuthPath("/")).toBe(false);
    expect(isPublicAuthPath("/invitations/accept")).toBe(false);
  });
});

describe("hasPublicSupabaseConfig", () => {
  it("is false when the URL or anon key is missing so the proxy stays signed-out", () => {
    expect(hasPublicSupabaseConfig(undefined, "anon")).toBe(false);
    expect(hasPublicSupabaseConfig("https://example.supabase.co", undefined)).toBe(
      false,
    );
    expect(hasPublicSupabaseConfig("", "anon")).toBe(false);
    expect(hasPublicSupabaseConfig("https://example.supabase.co", "")).toBe(false);
  });

  it("is true only when both public values are present", () => {
    expect(
      hasPublicSupabaseConfig("https://example.supabase.co", "anon-fixture"),
    ).toBe(true);
  });
});
