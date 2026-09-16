import { describe, expect, it } from "vitest";
import { classifyApiError } from "./api";
import {
  apiFailureBanner,
  chatRunFailureBanner,
  expectedRefusalCopy,
  GENERIC_PRODUCTION_ERROR,
  INSUFFICIENT_EVIDENCE_COPY,
  mutationFailureBanner,
  WEB_SEARCH_DISABLED_COPY,
  WEB_SEARCH_UNCONFIGURED_COPY,
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
    expect(
      apiFailureBanner(
        classifyApiError(503, { detail: "web_search_disabled" })!,
      ),
    ).toBe(WEB_SEARCH_DISABLED_COPY);
    expect(
      apiFailureBanner(
        classifyApiError(503, { detail: "web_search_unconfigured" })!,
      ),
    ).toBe(WEB_SEARCH_UNCONFIGURED_COPY);
    expect(
      apiFailureBanner(
        classifyApiError(503, { detail: "web_search_disabled" })!,
      ),
    ).not.toMatch(/Limiter fail-closed/);
  });

  it("maps empty completion protocol failure without traces", () => {
    expect(apiFailureBanner({ kind: "protocol", detail: "empty_answer" })).toBe(
      "The run completed without an answer.",
    );
  });

  it("maps insufficient evidence to company-source copy, not the generic fault", () => {
    expect(
      apiFailureBanner({ kind: "protocol", detail: "insufficient_evidence" }),
    ).toBe(INSUFFICIENT_EVIDENCE_COPY);
    expect(
      apiFailureBanner({ kind: "protocol", detail: "insufficient_evidence" }),
    ).not.toBe(GENERIC_PRODUCTION_ERROR);
    expect(expectedRefusalCopy("partial", "insufficient_evidence", [])).toBe(
      INSUFFICIENT_EVIDENCE_COPY,
    );
    expect(expectedRefusalCopy("error", "run_failed", [])).toBeNull();
  });

  it("maps run_failed to one generic alert without the internal code", () => {
    const failure = { kind: "protocol" as const, detail: "run_failed" };
    expect(apiFailureBanner(failure)).toBe(GENERIC_PRODUCTION_ERROR);
    expect(apiFailureBanner(failure)).not.toMatch(/run_failed/);
    expect(
      chatRunFailureBanner(failure, "62fc0f7e-61be-4e77-800e-8dae342b7884"),
    ).toBe("Something went wrong. Reference 62fc0f7e-61be-4e77-800e-8dae342b7884.");
    expect(chatRunFailureBanner(failure, null)).toBe(GENERIC_PRODUCTION_ERROR);
    expect(chatRunFailureBanner(failure, "62fc0f7e-61be-4e77-800e-8dae342b7884")).not.toMatch(
      /run_failed/,
    );
  });
});
