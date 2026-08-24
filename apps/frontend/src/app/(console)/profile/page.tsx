/**
 * Bookmark redirect from `/profile` to `/account`.
 */
import { redirect } from "next/navigation";

/**
 * Send legacy Profile bookmarks to the P08-14 destination.
 *
 * @returns Never. `redirect` throws.
 */
export default function ProfileRedirectPage() {
  redirect("/account");
}
