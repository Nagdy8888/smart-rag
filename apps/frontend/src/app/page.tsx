/**
 * Console home. Packet 2 keeps Phase 6 DeveloperApp chat/upload on `/`
 * after Auth. Sign-in is `/login`.
 */
import { DeveloperApp } from "../components/developer-app";

/**
 * Render the authenticated developer console.
 *
 * @returns DeveloperApp. AppShell comes from the root layout.
 */
export default function Home() {
  return <DeveloperApp />;
}
