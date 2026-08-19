/**
 * CSP connect-src construction for production versus development.
 */

import { describe, expect, it } from "vitest";
import {
  buildConnectSrcDirective,
  buildContentSecurityPolicy,
  buildScriptSrcDirective,
  originFromPublicUrl,
} from "../../next.config";

describe("originFromPublicUrl", () => {
  it("returns the origin and ignores a path", () => {
    expect(originFromPublicUrl("https://api.example.com/v1")).toBe(
      "https://api.example.com",
    );
  });

  it("returns null for missing or invalid values", () => {
    expect(originFromPublicUrl(undefined)).toBeNull();
    expect(originFromPublicUrl("")).toBeNull();
    expect(originFromPublicUrl("not-a-url")).toBeNull();
  });
});

describe("buildConnectSrcDirective", () => {
  it("fails closed in production without localhost or wildcard Auth", () => {
    const directive = buildConnectSrcDirective({
      nodeEnv: "production",
      apiBaseUrl: "https://rag-api.example.com",
      supabaseUrl: "https://qsjivtwtmlmtksufqjik.supabase.co",
    });
    expect(directive).toBe(
      "connect-src 'self' https://rag-api.example.com https://qsjivtwtmlmtksufqjik.supabase.co",
    );
    expect(directive).not.toContain("localhost");
    expect(directive).not.toContain("127.0.0.1");
    expect(directive).not.toContain("*.supabase.co");
  });

  it("omits loopback when production env is unset", () => {
    const directive = buildConnectSrcDirective({
      nodeEnv: "production",
      apiBaseUrl: undefined,
      supabaseUrl: undefined,
    });
    expect(directive).toBe("connect-src 'self'");
  });

  it("includes a loopback API origin when that is the configured URL", () => {
    const directive = buildConnectSrcDirective({
      nodeEnv: "production",
      apiBaseUrl: "http://127.0.0.1:8000",
      supabaseUrl: "https://qsjivtwtmlmtksufqjik.supabase.co",
    });
    expect(directive).toContain("http://127.0.0.1:8000");
    expect(directive).not.toContain("http://localhost:8000");
    expect(directive).not.toContain("http://127.0.0.1:54321");
  });

  it("adds local FastAPI and Auth loopback only in development", () => {
    const directive = buildConnectSrcDirective({
      nodeEnv: "development",
      apiBaseUrl: undefined,
      supabaseUrl: undefined,
    });
    expect(directive).toContain("http://127.0.0.1:8000");
    expect(directive).toContain("http://localhost:54321");
  });
});

describe("buildScriptSrcDirective", () => {
  it("keeps unsafe-eval out of production", () => {
    expect(buildScriptSrcDirective("production")).toBe(
      "script-src 'self' 'unsafe-inline'",
    );
    expect(buildScriptSrcDirective("development")).toContain("'unsafe-eval'");
  });
});

describe("buildContentSecurityPolicy", () => {
  it("includes the API origin in the production header value", () => {
    const policy = buildContentSecurityPolicy({
      nodeEnv: "production",
      apiBaseUrl: "https://rag-api.example.com",
      supabaseUrl: "https://qsjivtwtmlmtksufqjik.supabase.co",
    });
    expect(policy).toContain("https://rag-api.example.com");
    expect(policy).not.toContain("cdn.tailwindcss.com");
  });
});
