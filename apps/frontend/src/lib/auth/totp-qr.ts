/**
 * TOTP QR rendering rules for `auth.mfa.enroll({ factorType: "totp" })`.
 *
 * auth-js 2.71.1 documents `totp.qr_code` as SVG text that *may* be turned
 * into a data URL by the caller. This UI never injects that SVG as HTML.
 * An `<img>` is used only when the API already returned a
 * `data:image/...` URL.
 */

/**
 * Return an `<img src>` when enroll already produced a data-URL image.
 *
 * @param qrCode - `totp.qr_code` from enroll.
 * @returns Data URL, or null so callers show the secret as text instead.
 */
export function totpQrImageSrc(qrCode: string): string | null {
  if (qrCode.startsWith("data:image/")) {
    return qrCode;
  }
  return null;
}
