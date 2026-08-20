/**
 * Authenticated console route group: Stitch sidebar, top bar, main landmark.
 */
import type { ReactNode } from "react";
import { AppShell } from "../../components/ui/app-shell";

/**
 * Wrap Chat through Profile and invitation accept.
 *
 * @param children - Console route content.
 * @returns AppShell. Nav is not authorization.
 */
export default function ConsoleGroupLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
