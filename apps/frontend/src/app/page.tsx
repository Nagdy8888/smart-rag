/**
 * Console home. Packet 1 wraps the Phase 6 developer UI in AppShell.
 * Auth, chat, citations, and deletion still live in `DeveloperApp`.
 */
import { DeveloperApp } from "../components/developer-app";
import { AppShell } from "../components/ui/app-shell";

/**
 * Render the production shell around the existing developer console.
 *
 * @returns AppShell wrapping DeveloperApp. No new routes.
 */
export default function Home() {
  return (
    <AppShell>
      <DeveloperApp />
    </AppShell>
  );
}
