/**
 * Reviewed hostile and mixed-direction strings from `STITCH_BRIEF.md`.
 *
 * Render these only as React text nodes through `displayText`. They are
 * not HTML, not markdown, and not live diagnostics.
 */

/** Filename XSS fixture. Must not create an `img` or run `onerror`. */
export const XSS_FILENAME = "<img src=x onerror=alert(1)>.pdf";

/** Entity-label XSS fixture. Must remain inert text. */
export const XSS_ENTITY = "</script>شركة";

/** Mixed Arabic / English / URL fixture. Use `dir="auto"` isolation. */
export const MIXED_BIDI =
  "راجع INV-SR-8801 في https://example.com/q?id=12 — القسم 3.";
