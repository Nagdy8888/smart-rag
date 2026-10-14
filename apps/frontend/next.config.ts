import type { NextConfig } from "next";

/**
 * Next.js configuration for the console frontend image.
 *
 * `output: "standalone"` enables the non-root production Docker runner.
 *
 * Production `script-src` keeps `'unsafe-inline'` (no nonce). Next.js 16
 * nonce CSP requires a per-request nonce from `proxy()` plus dynamic
 * rendering so framework scripts receive that nonce. This app's CSP is a
 * static `next.config.ts` header and `proxy.ts` already owns Auth cookie
 * refresh; adding nonce here would be a large rewrite. `style-src` also
 * keeps `'unsafe-inline'` (PRD-L-003).
 *
 * `'unsafe-eval'` is development-only. Next.js documents that React uses
 * `eval` for debug info in development and that production React/Next do
 * not require `'unsafe-eval'` by default
 * (https://nextjs.org/docs/app/guides/content-security-policy).
 *
 * `connect-src` uses exact `NEXT_PUBLIC_API_BASE_URL` and
 * `NEXT_PUBLIC_SUPABASE_URL` origins. Loopback hosts are added only when
 * `NODE_ENV=development`. Production never ships hardcoded localhost or
 * a wildcard supabase.co host.
 *
 * `devIndicators: false` hides the Next.js route badge in `next dev` so
 * Playwright visual snapshots match production chrome.
 */

/** Inputs used to build the CSP `connect-src` directive. */
export type ConnectSrcEnv = {
  nodeEnv: string | undefined;
  apiBaseUrl: string | undefined;
  supabaseUrl: string | undefined;
  glitchtipDsn?: string | undefined;
};

const DEV_LOOPBACK_ORIGINS = [
  "http://127.0.0.1:8000",
  "http://localhost:8000",
] as const;

/**
 * Return the origin of a public URL, or null when the value is missing or
 * not a valid absolute URL.
 *
 * @param value - `NEXT_PUBLIC_API_BASE_URL` or `NEXT_PUBLIC_SUPABASE_URL`.
 * @returns Scheme plus host (and port when non-default), or null.
 */
export function originFromPublicUrl(value: string | undefined): string | null {
  if (value === undefined) {
    return null;
  }
  const trimmed = value.trim();
  if (trimmed === "") {
    return null;
  }
  try {
    return new URL(trimmed).origin;
  } catch {
    return null;
  }
}

/**
 * Build the CSP `connect-src` directive.
 *
 * Production includes `'self'` plus the exact API and Auth origins when
 * those env vars parse. A GlitchTip DSN adds only that DSN origin.
 * Development also allows local FastAPI loopback ports. Missing production
 * env fails closed (no localhost fallback, no `*.supabase.co` wildcard).
 *
 * @param env - `NODE_ENV`, public API/Auth URLs, and optional GlitchTip DSN.
 * @returns Full `connect-src …` directive.
 */
export function buildConnectSrcDirective(env: ConnectSrcEnv): string {
  const origins = new Set<string>();
  const apiOrigin = originFromPublicUrl(env.apiBaseUrl);
  const authOrigin = originFromPublicUrl(env.supabaseUrl);
  const glitchtipOrigin = originFromPublicUrl(env.glitchtipDsn);
  if (apiOrigin !== null) {
    origins.add(apiOrigin);
  }
  if (authOrigin !== null) {
    origins.add(authOrigin);
  }
  if (glitchtipOrigin !== null) {
    origins.add(glitchtipOrigin);
  }
  if (env.nodeEnv === "development") {
    for (const extra of DEV_LOOPBACK_ORIGINS) {
      origins.add(extra);
    }
  }
  const extras = [...origins].join(" ");
  return extras === "" ? "connect-src 'self'" : `connect-src 'self' ${extras}`;
}

/**
 * Build the CSP `script-src` directive.
 *
 * @param nodeEnv - `NODE_ENV`.
 * @returns Development includes `'unsafe-eval'`; production does not.
 */
export function buildScriptSrcDirective(nodeEnv: string | undefined): string {
  if (nodeEnv === "development") {
    return "script-src 'self' 'unsafe-inline' 'unsafe-eval'";
  }
  return "script-src 'self' 'unsafe-inline'";
}

/**
 * Build the full Content-Security-Policy header value.
 *
 * @param env - Same inputs as `buildConnectSrcDirective`.
 * @returns Semicolon-separated CSP policy.
 */
export function buildContentSecurityPolicy(env: ConnectSrcEnv): string {
  return [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "font-src 'self'",
    "img-src 'self' data:",
    "style-src 'self' 'unsafe-inline'",
    buildScriptSrcDirective(env.nodeEnv),
    buildConnectSrcDirective(env),
    "form-action 'self'",
  ].join("; ");
}

const contentSecurityPolicy = buildContentSecurityPolicy({
  nodeEnv: process.env.NODE_ENV,
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL,
  glitchtipDsn: process.env.NEXT_PUBLIC_GLITCHTIP_DSN,
});

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  devIndicators: false,
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "no-referrer" },
          { key: "X-DNS-Prefetch-Control", value: "off" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
          {
            key: "Content-Security-Policy",
            value: contentSecurityPolicy,
          },
        ],
      },
    ];
  },
};

export default nextConfig;
