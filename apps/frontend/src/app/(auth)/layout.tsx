/**
 * Public Auth route group: focused card layout, no console navigation.
 */
import type { ReactNode } from "react";
import { AuthLayout } from "../../components/auth/auth-layout";

/**
 * Wrap login, signup, reset, invitation accept, and unavailable pages.
 *
 * @param children - Auth route content.
 * @returns AuthLayout. URLs are unchanged by this group.
 */
export default function AuthGroupLayout({ children }: { children: ReactNode }) {
  return <AuthLayout>{children}</AuthLayout>;
}
