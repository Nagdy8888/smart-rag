/**
 * Shared HTML shell. Route groups supply Auth vs console chrome.
 */
import type { Metadata } from "next";
import { AppProviders } from "../components/providers";
import "./globals.css";

export const metadata: Metadata = {
  title: "Smart RAG",
  description: "Ask questions about your company documents and get cited answers.",
};

/**
 * Render the root document for every App Router page.
 *
 * @param children - Auth or console layout content.
 * @returns English LTR html/body with providers. No AppShell here.
 * @remarks
 * Google Fonts and CDN typefaces are forbidden. IBM Plex is self-hosted.
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
