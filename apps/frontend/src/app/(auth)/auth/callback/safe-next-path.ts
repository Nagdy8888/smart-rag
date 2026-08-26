/**
 * Same-origin callback redirect helper.
 *
 * This is the server-side security gate for the Auth `next` parameter.
 * Client checks are convenience only.
 */

const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;
const MALFORMED_PERCENT = /%(?![0-9A-Fa-f]{2})/;
const ENCODED_BACKSLASH = /%5c/i;

/**
 * Return a same-origin root-relative path or `/`.
 *
 * Rejects absolute URLs, protocol-relative hosts, any backslash, encoded
 * slash/backslash ambiguity, control characters, userinfo, malformed percent
 * encoding, and a parsed origin that differs from `requestOrigin`. Valid path,
 * query, and fragment are preserved only after same-origin parsing.
 *
 * @param raw - Untrusted `next` query value.
 * @param requestOrigin - Origin of the callback request, for example
 *   `https://app.example`.
 * @returns Application-relative path starting with `/`.
 * @remarks
 * Security: this function is the authoritative open-redirect check for the
 * PKCE callback. It does not perform network I/O.
 */
export function safeNextPath(
  raw: string | null,
  requestOrigin: string,
): string {
  if (raw === null || raw === "") {
    return "/";
  }
  if (
    raw.includes("\\") ||
    ENCODED_BACKSLASH.test(raw) ||
    CONTROL_CHARS.test(raw) ||
    MALFORMED_PERCENT.test(raw)
  ) {
    return "/";
  }
  let decoded: string;
  try {
    decoded = decodeURIComponent(raw);
  } catch {
    return "/";
  }
  if (
    decoded.includes("\\") ||
    CONTROL_CHARS.test(decoded) ||
    !decoded.startsWith("/") ||
    decoded.startsWith("//")
  ) {
    return "/";
  }
  let parsed: URL;
  let expected: URL;
  try {
    expected = new URL(requestOrigin);
    parsed = new URL(decoded, expected);
  } catch {
    return "/";
  }
  if (
    parsed.origin !== expected.origin ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    parsed.pathname.startsWith("//")
  ) {
    return "/";
  }
  const next = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  return next.startsWith("/") ? next : "/";
}
