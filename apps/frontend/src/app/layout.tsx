import type { Metadata } from "next";
import { AppProviders } from "../components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart RAG console",
  description:
    "Production console shell hosting the Phase 6 developer console until later Phase 8 packets replace that surface.",
};

/**
 * Render the shared HTML shell for console routes.
 *
 * @param children - App Router content for the active route.
 * @returns The root document with English LTR chrome and the system font stack.
 * @remarks
 * Google Fonts and CDN typefaces are forbidden by the CSP/token contract.
 * Fonts are the STITCH_BRIEF system stack in `globals.css`.
 */
export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" dir="ltr">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
