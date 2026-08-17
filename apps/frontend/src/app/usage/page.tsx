/**
 * Usage meters, 402/rate copy, and GAP-07-11/12 Unavailable.
 */
import { UsageApp } from "../../components/usage-app";

/**
 * Render GET /usage/me and company totals. No budget sliders.
 *
 * @returns Usage surface.
 */
export default function UsagePage() {
  return <UsageApp />;
}
