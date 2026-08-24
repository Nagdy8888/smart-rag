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


describe("approved HTTP failure copy", () => {
  it("maps 402, 403, 404, 409, 422, 426, 429, and 503 to safe banners", () => {
    expect(
      apiFailureBanner(classifyApiError(402, { detail: "budget_exhausted" })!),
    ).toContain("Budget exhausted");
    expect(
      apiFailureBanner(
        classifyApiError(403, { detail: "forbidden" })!,
      ),
    ).toContain("forbidden");
    expect(apiFailureBanner(classifyApiError(404, {})!)).toContain("deleted");
    expect(
      apiFailureBanner(classifyApiError(409, { detail: "conflict" })!),
    ).toContain("conflict");
    expect(
      apiFailureBanner(classifyApiError(422, { detail: "validation_error" })!),
    ).toContain("invalid");
    expect(
      apiFailureBanner(
        classifyApiError(426, {
          min_client_version: "9.0.0",
          sse_schema_version: "1",
        })!,
      ),
    ).toContain("min_client_version");
    expect(
      apiFailureBanner(
        classifyApiError(
          429,
          { detail: "rate_limited" },
          { "Retry-After": "12" },
        )!,
      ),
    ).toContain("Retry-After 12");
    expect(
      apiFailureBanner(
        classifyApiError(503, { detail: "limiter_unavailable" })!,
      ),
    ).toContain("fail-closed");
  });

  it("maps empty completion protocol failure without traces", () => {
    expect(apiFailureBanner({ kind: "protocol", detail: "empty_answer" })).toBe(
      "The run completed without an answer.",
    );
  });
});
