/**
 * Auto chat at `/`. Replaces the Phase 6 DeveloperApp monolith.
 */
import { ChatApp } from "../../components/chat-app";

/**
 * Render the authenticated Auto chat surface.
 *
 * @returns ChatApp. AppShell comes from the console route group.
 */
export default function Home() {
  return <ChatApp />;
}
