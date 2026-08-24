/**
 * Ask at `/`. Replaces the Phase 6 DeveloperApp monolith.
 */
import { ChatApp } from "../../components/chat/chat-app";

/**
 * Render the authenticated Ask surface.
 *
 * @returns ChatApp. AppShell comes from the console route group.
 */
export default function Home() {
  return <ChatApp />;
}
