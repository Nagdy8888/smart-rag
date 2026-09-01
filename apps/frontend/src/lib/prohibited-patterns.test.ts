/**
 * Fail production frontend source on prohibited generated-HTML patterns.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontendRoot = path.join(here, "../..");
const srcRoot = path.join(frontendRoot, "src");

const SKIP_NAMES = new Set([
  "design-tokens.test.ts",
  "prohibited-patterns.test.ts",
  "hostile-text-fixtures.ts",
]);

const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".css", ".mjs", ".mts"]);

/**
 * List App Router folder names, flattening Next.js route groups.
 *
 * @param appDir - `src/app` path.
 * @returns Top-level and grouped route folder names.
 */
function appRouteNames(appDir: string): string[] {
  const names: string[] = [];
  for (const entry of readdirSync(appDir)) {
    if (entry.startsWith("(") && entry.endsWith(")")) {
      names.push(...readdirSync(path.join(appDir, entry)));
      continue;
    }
    names.push(entry);
  }
  return names;
}

/**
 * Recursively list source files under a directory.
 *
 * @param directory - Start path.
 * @returns Absolute file paths.
 */
function walk(directory: string): string[] {
  const found: string[] = [];
  for (const entry of readdirSync(directory)) {
    if (entry === "node_modules" || entry === ".next") {
      continue;
    }
    const full = path.join(directory, entry);
    const info = statSync(full);
    if (info.isDirectory()) {
      found.push(...walk(full));
      continue;
    }
    if (entry.endsWith(".test.ts") || entry.endsWith(".test.tsx")) {
      continue;
    }
    if (SKIP_NAMES.has(entry)) {
      continue;
    }
    if (SOURCE_EXTENSIONS.has(path.extname(entry))) {
      found.push(full);
    }
  }
  return found;
}

describe("prohibited production patterns", () => {
  const files = [
    ...walk(srcRoot),
    path.join(frontendRoot, "next.config.ts"),
    path.join(frontendRoot, "postcss.config.mjs"),
  ];

  it("rejects CDN, innerHTML, dead hashes, blur, fonts, avatars, and random auth", () => {
    const hits: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      const rel = path.relative(frontendRoot, file).replaceAll("\\", "/");
      const needles: Array<[RegExp, string]> = [
        [/cdn\.tailwindcss\.com/i, "Tailwind CDN"],
        [/dangerouslySetInnerHTML/, "dangerouslySetInnerHTML"],
        [/\.innerHTML\b/, "innerHTML mutation"],
        [/href\s*=\s*(["'])#\1/, "href hash placeholder"],
        [/backdrop-filter/i, "backdrop-filter"],
        [/\bblur\s*\(/, "blur("],
        [/fonts\.googleapis\.com/, "Google Fonts CSS"],
        [/fonts\.gstatic\.com/, "Google Fonts files"],
        [/fonts\.google\.com/, "Google Fonts"],
        [/next\/font\/google/, "next/font/google"],
        [/materialsymbols/i, "Material Symbols CDN"],
        [/placeholder\.com/, "placeholder avatars"],
        [/i\.pravatar\.cc/, "pravatar"],
        [/Math\.random\s*\(/, "Math.random live diagnostics/auth"],
        [/stitch_smart_rag_enterprise_console/, "gitignored Stitch import"],
      ];
      for (const [pattern, label] of needles) {
        if (pattern.test(text)) {
          hits.push(`${rel}: ${label}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });

  it("does not add Stitch frame or design-system product routes", () => {
    const appDir = path.join(srcRoot, "app");
    const names = appRouteNames(appDir);
    expect(names).not.toContain("frame_00");
    expect(names).not.toContain("design-system");
    expect(names).not.toContain("gallery");
    expect(names).not.toContain("chat");
    expect(names).not.toContain("docs");
    expect(names).not.toContain("gallery");
    expect(names.some((name) => name.startsWith("frame_"))).toBe(false);
    expect(names).toEqual(
      expect.arrayContaining([
        "documents",
        "graph",
        "tables",
        "admin",
        "account",
        "team",
        "tools",
        "curation",
        "usage",
        "profile",
      ]),
    );
  });

  it("ships a DELETE /documents client and keeps citation href null", () => {
    const api = readFileSync(path.join(srcRoot, "lib/api.ts"), "utf8");
    expect(api).toContain("deleteDocument");
    const documents = readFileSync(path.join(srcRoot, "lib/api/documents.ts"), "utf8");
    expect(documents).toContain("deleteDocument");
    expect(documents).toMatch(/method:\s*"DELETE"/);
    const drawer = readFileSync(path.join(srcRoot, "lib/citation-drawer.ts"), "utf8");
    expect(drawer).toContain("return null");
    expect(drawer).not.toContain("DOCUMENT_DELETE_UNAVAILABLE");
  });

  it("allows Auth-direct App Router folders", () => {
    const names = appRouteNames(path.join(srcRoot, "app"));
    expect(names).toEqual(
      expect.arrayContaining(["login", "signup", "auth", "invitations"]),
    );
    expect(names).not.toContain("mfa");
    expect(names).not.toContain("unavailable");
  });

  it("does not embed service-role or privileged keys in frontend source", () => {
    const hits: string[] = [];
    for (const file of files) {
      const text = readFileSync(file, "utf8");
      const rel = path.relative(frontendRoot, file).replaceAll("\\", "/");
      const needles: Array<[RegExp, string]> = [
        [/NEXT_PUBLIC_[A-Z0-9_]*SERVICE_ROLE/, "NEXT_PUBLIC service role"],
        [/process\.env\.[A-Z0-9_]*SERVICE_ROLE/, "process.env service role"],
        [/supabaseServiceRole/i, "service role identifier"],
        [/test-auth-bypass/i, "test-auth bypass"],
      ];
      for (const [pattern, label] of needles) {
        if (pattern.test(text)) {
          hits.push(`${rel}: ${label}`);
        }
      }
    }
    expect(hits).toEqual([]);
  });

  it("keeps production CSP without CDN hosts, wildcard Auth, or always-on unsafe-eval", () => {
    const config = readFileSync(path.join(frontendRoot, "next.config.ts"), "utf8");
    expect(config).toContain("X-Content-Type-Options");
    expect(config).toContain("nosniff");
    expect(config).toContain("X-Frame-Options");
    expect(config).toContain("DENY");
    expect(config).toContain("Referrer-Policy");
    expect(config).toContain("no-referrer");
    expect(config).toContain("Content-Security-Policy");
    expect(config).toContain("font-src 'self'");
    expect(config).toContain("img-src 'self' data:");
    expect(config).toContain("Permissions-Policy");
    expect(config).toContain("X-DNS-Prefetch-Control");
    expect(config).not.toMatch(/cdn\.tailwindcss\.com/);
    expect(config).not.toMatch(/fonts\.googleapis\.com/);
    expect(config).toContain("nodeEnv === \"development\"");
    expect(config).toContain("'unsafe-eval'");
    expect(config).toContain("buildConnectSrcDirective");
    expect(config).toContain("NEXT_PUBLIC_API_BASE_URL");
    expect(config).toContain("NEXT_PUBLIC_SUPABASE_URL");
    expect(config).not.toMatch(/connect-src 'self' http:\/\/127\.0\.0\.1:8000 http:\/\/localhost:8000/);
  });

  it("does not send X-Test headers from api.ts", () => {
    const api = readFileSync(path.join(srcRoot, "lib/api.ts"), "utf8");
    expect(api).not.toMatch(/["']X-Test-/);
  });
});
