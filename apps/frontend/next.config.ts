import type { NextConfig } from "next";

/**
 * Next.js configuration for the console frontend image.
 *
 * `output: "standalone"` enables the non-root production Docker runner.
 * CSP is a baseline; connect-src allows local FastAPI and Supabase Auth.
 */
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
          {
            key: "Content-Security-Policy",
            value:
              "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; font-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; connect-src 'self' http://127.0.0.1:8000 http://localhost:8000 http://127.0.0.1:54321 http://localhost:54321 https://*.supabase.co",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
