/**
 * Usage meters, 402/rate copy, and honest unavailable budget/audit states.
 */
import { UsageApp } from "../../../components/usage-app";

/**
 * Render GET /usage/me and company totals. No budget sliders.
 *
 * @returns Usage surface.
 */
export default function UsagePage() {
  return <UsageApp />;
}
