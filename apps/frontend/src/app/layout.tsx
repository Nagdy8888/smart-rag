import type { Metadata } from "next";
import { AppProviders } from "../components/providers";
import { AppShell } from "../components/ui/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart RAG console",
  description: "Smart RAG console (release candidate)",
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
        <AppProviders>
          <AppShell>{children}</AppShell>
        </AppProviders>
      </body>
    </html>
  );
}
