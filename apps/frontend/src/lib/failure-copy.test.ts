import { describe, expect, it } from "vitest";
import { classifyApiError } from "./api";
import {
  apiFailureBanner,
  GENERIC_PRODUCTION_ERROR,
  mutationFailureBanner,
} from "./failure-copy";

describe("generic production errors", () => {
  it("maps unknown 5xx to Something went wrong", () => {
    const failure = classifyApiError(500, {
      detail: "Traceback (most recent call last): InternalServerError",
    });
    expect(failure).not.toBeNull();
    expect(apiFailureBanner(failure!)).toBe(GENERIC_PRODUCTION_ERROR);
    expect(apiFailureBanner(failure!)).not.toMatch(/Traceback|InternalServerError/);
  });

  it("does not echo Error.message for unknown mutations", () => {
    const banner = mutationFailureBanner(
      new Error("AuthApiError: Invalid login credentials from GoTrue"),
    );
    expect(banner).toBe(GENERIC_PRODUCTION_ERROR);
    expect(banner).not.toMatch(/GoTrue|AuthApiError|Invalid login/);
  });
});
