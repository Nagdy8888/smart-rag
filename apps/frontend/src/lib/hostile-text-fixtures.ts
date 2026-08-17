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

/** RTL paragraph with mixed LTR code from the brief. */
export const MIXED_POLICY_CODE = "الكود Policy-أ-14 ساري.";

/** Isolated LTR code inside the mixed policy sentence. */
export const MIXED_POLICY_CODE_ISOLATE = "Policy-أ-14";

/** Diacritic fixture. Line-height must be 1.75 with no clip. */
export const DIACRITICS_AR = "إِنَّ";

/** Long URL that must wrap inside a bidi isolate, not the page. */
export const LONG_URL =
  "https://intranet.example.invalid/procurement/2024/Q3/invoice-8801?lang=ar";

/** `javascript:` href candidate. Must fail `isSafeHttpUrl`. */
export const XSS_JAVASCRIPT_URL = "javascript:alert(1)";

/** Bidi-control payload. Must remain a text node, never reorder chrome. */
export const BIDI_CONTROL = "safe\u202Efilename.exe.pdf";

/** Canonical logical-highlight sentence. Offsets 7–11 select ACME. */
export const CITATION_LOGICAL_SENTENCE = "الشركة ACME وقعت العقد.";
