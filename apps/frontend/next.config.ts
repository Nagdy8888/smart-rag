import type { NextConfig } from "next";

/**
 * Next.js configuration for the console frontend image.
 *
 * `output: "standalone"` enables the non-root production Docker runner.
 * CSP is a baseline; connect-src allows local FastAPI and Supabase Auth.
 *
 * `'unsafe-eval'` is development-only. Next.js documents that React uses
 * `eval` for debug info in development and that production React/Next do
 * not require `'unsafe-eval'` by default
 * (https://nextjs.org/docs/app/guides/content-security-policy).
 */
const isDev = process.env.NODE_ENV === "development";

const scriptSrc = isDev
  ? "'self' 'unsafe-inline' 'unsafe-eval'"
  : "'self' 'unsafe-inline'";

const contentSecurityPolicy = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "frame-ancestors 'none'",
  "font-src 'self'",
  "img-src 'self' data:",
  "style-src 'self' 'unsafe-inline'",
  `script-src ${scriptSrc}`,
  "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000 http://127.0.0.1:54321 http://localhost:54321 https://*.supabase.co",
  "form-action 'self'",
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
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
