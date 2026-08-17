/**
 * Convenience role helpers. Hidden chrome is not authorization.
 * FastAPI still 403s forged requests.
 */

/** Owner or admin. Crawl/retry convenience may show. */
export function isOwnerOrAdmin(role: string | undefined): boolean {
  return role === "owner" || role === "admin";
}

/** Viewer role. Upload convenience is hidden; server still denies. */
export function isViewerRole(role: string | undefined): boolean {
  return role === "viewer";
}

/**
 * Return whether the upload drop-zone should render.
 *
 * @param role - `GET /me` role.
 * @param uploadEnabled - Server `upload_enabled`.
 * @returns Convenience flag only.
 */
export function showUploadConvenience(
  role: string | undefined,
  uploadEnabled: boolean | undefined,
): boolean {
  if (isViewerRole(role)) {
    return false;
  }
  return uploadEnabled === true;
}

/**
 * Return whether the crawl form should render.
 *
 * @param role - `GET /me` role.
 * @returns Convenience flag. Members still 403 if they call the helper.
 */
export function showCrawlConvenience(role: string | undefined): boolean {
  return isOwnerOrAdmin(role);
}
