import { describe, expect, it } from "vitest";
import {
  classifyApiError,
  fetchReady,
  paidMutationHeaders,
  resumeHeaders,
  startMessageStream,
} from "./api";
import { CLIENT_VERSION } from "./client-version";

describe("paidMutationHeaders", () => {
  it("sends handshake and idempotency on new paid work", () => {
    const headers = paidMutationHeaders(
      { accessToken: "jwt-token" },
      "11111111-1111-4111-8111-111111111111",
    );
    expect(headers["X-Client-Version"]).toBe(CLIENT_VERSION);
    expect(headers["Idempotency-Key"]).toBe(
      "11111111-1111-4111-8111-111111111111",
    );
    expect(headers.Authorization).toBe("Bearer jwt-token");
  });
});

describe("resumeHeaders", () => {
  it("omits X-Client-Version on resume", () => {
    const headers = resumeHeaders({ accessToken: "jwt-token" }, "12");
    expect(headers["X-Client-Version"]).toBeUndefined();
    expect(headers["Last-Event-ID"]).toBe("12");
  });
});

describe("classifyApiError", () => {
  it("maps 426 to an upgrade banner", () => {
    const failure = classifyApiError(426, {
      min_client_version: "0.2.0",
      sse_schema_version: "2",
    });
    expect(failure).toEqual({
      kind: "upgrade",
      minClientVersion: "0.2.0",
      sseSchemaVersion: "2",
    });
  });

  it("maps 403 MFA required to an MFA banner", () => {
    expect(classifyApiError(403, { detail: "MFA required" })).toEqual({
      kind: "mfa",
      detail: "MFA required",
    });
  });

  it("maps 401 to session-revoked auth", () => {
    expect(classifyApiError(401, { detail: "session_revoked" })).toEqual({
      kind: "auth",
      status: 401,
      detail: "session_revoked",
    });
  });

  it("maps 503 to limiter fail-closed", () => {
    expect(classifyApiError(503, { detail: "limiter_unavailable" })).toEqual({
      kind: "fail_closed",
      status: 503,
      detail: "limiter_unavailable",
    });
  });

  it("maps 404 to deleted conversation", () => {
    expect(classifyApiError(404, {})).toEqual({ kind: "deleted" });
  });
});

describe("startMessageStream", () => {
  it("admits with JSON then resumes GET events for the same run", async () => {
    const calls: string[] = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      if (url.includes("/messages")) {
        const headers = init?.headers as Record<string, string>;
        expect(headers.Accept).toBe("application/json");
        expect(headers["X-Client-Version"]).toBe(CLIENT_VERSION);
        expect(headers["Idempotency-Key"]).toBe(
          "33333333-3333-4333-8333-333333333333",
        );
        return new Response(
          JSON.stringify({
            run_id: "44444444-4444-4444-8444-444444444444",
            stream_path: "/runs/44444444-4444-4444-8444-444444444444/events",
            reconnect: false,
            reservation_id: "55555555-5555-4555-8555-555555555555",
            route_family: "composite",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      expect(url).toContain(
        "/runs/44444444-4444-4444-8444-444444444444/events?after=0",
      );
      return new Response(
        'event: schema\ndata: {"sse_schema_version":"1"}\n\n',
        {
          status: 200,
          headers: { "Content-Type": "text/event-stream" },
        },
      );
    };
    const started = await startMessageStream(
      { accessToken: "jwt-token" },
      "66666666-6666-4666-8666-666666666666",
      "<script>alert(1)</script>",
      "33333333-3333-4333-8333-333333333333",
      fetchImpl,
    );
    expect(started.failure).toBeNull();
    expect(started.admission?.run_id).toBe(
      "44444444-4444-4444-8444-444444444444",
    );
    expect(calls).toHaveLength(2);
    expect(calls[0]?.startsWith("POST")).toBe(true);
    expect(calls[1]?.startsWith("GET")).toBe(true);
  });
});

describe("fetchReady", () => {
  it("maps GET /health/ready including paradedb", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          status: "degraded",
          query_ready: false,
          detail: "mock",
          rate_limit_degraded: false,
          dependencies: [
            { name: "paradedb", status: "down" },
            { name: "lightrag", status: "unconfigured" },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    const ready = await fetchReady(fetchImpl);
    expect(ready?.query_ready).toBe(false);
    expect(ready?.dependencies).toEqual([
      { name: "paradedb", status: "down" },
      { name: "lightrag", status: "unconfigured" },
    ]);
  });
});
