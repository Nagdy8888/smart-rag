import { describe, expect, it } from "vitest";
import { mfaRecoveryFormMaySubmit, mfaRecoveryRequestUrl, MFA_RECOVERY_HTTP_ENABLED } from "./mfa-recovery";
import { totpQrImageSrc } from "./totp-qr";
import { isPublicAuthPath } from "./paths";

describe("MFA recovery gap", () => {
  it("does not expose an HTTP recovery endpoint", () => {
    expect(MFA_RECOVERY_HTTP_ENABLED).toBe(false);
    expect(mfaRecoveryRequestUrl()).toBeNull();
    expect(mfaRecoveryFormMaySubmit()).toBe(false);
  });
});

describe("totp QR src", () => {
  it("uses an img only for data-URL qr_code values", () => {
    expect(totpQrImageSrc("data:image/png;base64,abc")).toBe(
      "data:image/png;base64,abc",
    );
    expect(totpQrImageSrc("<svg xmlns='http://www.w3.org/2000/svg'></svg>")).toBeNull();
  });
});

describe("public auth paths", () => {
  it("allows Auth-direct routes without treating them as the security boundary", () => {
    expect(isPublicAuthPath("/review-fixtures")).toBe(true);
    expect(isPublicAuthPath("/signup")).toBe(true);
    expect(isPublicAuthPath("/mfa/challenge")).toBe(true);
    expect(isPublicAuthPath("/unavailable/GAP-07-07")).toBe(true);
    expect(isPublicAuthPath("/")).toBe(false);
    expect(isPublicAuthPath("/invitations/accept")).toBe(false);
  });
});
