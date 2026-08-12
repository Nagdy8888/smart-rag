import type { NextConfig } from "next";

/**
 * Next.js configuration for the foundation frontend image.
 *
 * `output: "standalone"` enables the non-root production Docker runner.
 */
const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
