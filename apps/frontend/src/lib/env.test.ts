import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBaseUrl, publicSupabaseConfig } from "./env";

describe("public browser environment", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("defaults the API origin outside production", () => {
    vi.stubEnv("NODE_ENV", "development");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    expect(apiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("fails closed in production without public API or Auth values", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    expect(() => apiBaseUrl()).toThrow(/NEXT_PUBLIC_API_BASE_URL/);
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");
    expect(() => publicSupabaseConfig()).toThrow(/NEXT_PUBLIC_SUPABASE/);
  });

  it("returns hosted public Auth when both values are present", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "https://api.example/");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-fixture");
    expect(apiBaseUrl()).toBe("https://api.example");
    expect(publicSupabaseConfig()).toEqual({
      url: "https://example.supabase.co",
      anonKey: "anon-fixture",
    });
  });
});
