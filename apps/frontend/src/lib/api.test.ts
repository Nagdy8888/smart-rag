import { describe, expect, it } from "vitest";
import {
  acceptInvitation,
  analyzeTable,
  classifyApiError,
  enqueueWebsiteCrawl,
  fetchDocument,
  fetchReady,
  finalizeUpload,
  inspectGraph,
  paidMutationHeaders,
  reserveUpload,
  resumeHeaders,
  shouldResumeExistingRun,
  startMessageStream,
  startOrResumeMessageStream,
} from "./api";
import { clientComputedTableTotal } from "./table-plan";
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

  it("maps 402 budget_exhausted", () => {
    expect(classifyApiError(402, { detail: "budget_exhausted" })).toEqual({
      kind: "budget",
      detail: "budget_exhausted",
    });
  });

  it("maps 429 rate_limited with Retry-After", () => {
    expect(
      classifyApiError(
        429,
        { detail: "rate_limited" },
        { "Retry-After": "12" },
      ),
    ).toEqual({
      kind: "rate",
      detail: "rate_limited",
      retryAfter: "12",
    });
  });

  it("maps 429 concurrency_limit", () => {
    expect(classifyApiError(429, { detail: "concurrency_limit" })).toEqual({
      kind: "rate",
      detail: "concurrency_limit",
      retryAfter: null,
    });
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

describe("startOrResumeMessageStream", () => {
  it("prefers resume GET when runId is set and terminal is null", async () => {
    const calls: string[] = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      expect(url).toContain("/runs/run-1/events?after=4");
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Client-Version"]).toBeUndefined();
      return new Response("event: heartbeat\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    };
    const started = await startOrResumeMessageStream(
      { accessToken: "jwt-token" },
      "conv-1",
      "retry",
      {
        runId: "run-1",
        terminal: null,
        lastSequence: 4,
        idempotencyKey: "33333333-3333-4333-8333-333333333333",
      },
      fetchImpl,
    );
    expect(started.resumed).toBe(true);
    expect(started.failure).toBeNull();
    expect(calls).toEqual(["GET http://127.0.0.1:8000/runs/run-1/events?after=4"]);
    expect(calls.some((call) => call.startsWith("POST"))).toBe(false);
  });

  it("posts once when no run exists yet", async () => {
    expect(
      shouldResumeExistingRun({
        runId: null,
        terminal: null,
        lastSequence: 0,
        idempotencyKey: "k",
      }),
    ).toBe(false);
    const fetchImpl: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes("/messages")) {
        return new Response(
          JSON.stringify({
            run_id: "run-2",
            stream_path: "/runs/run-2/events",
            reconnect: false,
            reservation_id: "res-2",
            route_family: "composite",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("event: schema\ndata: {\"sse_schema_version\":\"1\"}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    };
    const started = await startOrResumeMessageStream(
      { accessToken: "jwt-token" },
      "conv-1",
      "hello",
      {
        runId: null,
        terminal: null,
        lastSequence: 0,
        idempotencyKey: "33333333-3333-4333-8333-333333333333",
      },
      fetchImpl,
    );
    expect(started.resumed).toBe(false);
    expect(started.admission?.run_id).toBe("run-2");
  });
});

describe("acceptInvitation", () => {
  it("posts { token } only", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Test-Role"]).toBeUndefined();
      expect(headers.Authorization).toBe("Bearer jwt-token");
      return new Response(
        JSON.stringify({ invitation_id: "inv-1" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const accepted = await acceptInvitation(
      { accessToken: "jwt-token" },
      "raw-token-value",
      fetchImpl,
    );
    expect(JSON.parse(body)).toEqual({ token: "raw-token-value" });
    expect(accepted.invitation_id).toBe("inv-1");
  });
});

describe("submitMessageBody Auto contract", () => {
  it("posts message and idempotency_key only, with no route field", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      if (url.includes("/messages")) {
        body = String(init?.body ?? "");
        const headers = init?.headers as Record<string, string>;
        expect(headers["X-Test-User-Id"]).toBeUndefined();
        expect(headers["X-Test-Role"]).toBeUndefined();
        return new Response(
          JSON.stringify({
            run_id: "run-auto",
            stream_path: "/runs/run-auto/events",
            reconnect: false,
            reservation_id: "res-auto",
            route_family: "composite",
            status: "pending",
          }),
          { status: 202, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response("event: schema\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    };
    await startMessageStream(
      { accessToken: "jwt-token" },
      "conv-1",
      "hello",
      "33333333-3333-4333-8333-333333333333",
      fetchImpl,
    );
    const parsed = JSON.parse(body) as Record<string, unknown>;
    expect(parsed).toEqual({
      message: "hello",
      idempotency_key: "33333333-3333-4333-8333-333333333333",
    });
    expect(parsed.route).toBeUndefined();
    expect(parsed.route_family).toBeUndefined();
  });
});

describe("finalizeUpload", () => {
  it("posts required finalize fields", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Test-Role"]).toBeUndefined();
      return new Response(
        JSON.stringify({
          reservation_id: "res-1",
          document_id: "doc-1",
          version_id: "ver-1",
          job_id: "job-1",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const result = await finalizeUpload(
      { accessToken: "jwt-token" },
      {
        reservation_id: "res-1",
        object_name: "user/res/file.pdf",
        content_hash: "a".repeat(64),
        actual_bytes: 12,
        declared_category: "allowed",
        attestation_policy_version: "2026-08-13",
        idempotency_key: "idem-finalize-1",
      },
      fetchImpl,
    );
    const parsed = JSON.parse(body) as Record<string, unknown>;
    expect(parsed.reservation_id).toBe("res-1");
    expect(parsed.object_name).toBe("user/res/file.pdf");
    expect(parsed.content_hash).toHaveLength(64);
    expect(parsed.actual_bytes).toBe(12);
    expect(parsed.declared_category).toBe("allowed");
    expect(parsed.attestation_policy_version).toBe("2026-08-13");
    expect(parsed.idempotency_key).toBe("idem-finalize-1");
    expect(result.document_id).toBe("doc-1");
  });
});

describe("enqueueWebsiteCrawl", () => {
  it("still posts for a member helper call (server 403 is authoritative)", async () => {
    const fetchImpl: typeof fetch = async (_input, init) => {
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Test-Role"]).toBeUndefined();
      return new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    };
    await expect(
      enqueueWebsiteCrawl(
        { accessToken: "jwt-token" },
        {
          start_url: "https://example.com",
          approved_domain: "example.com",
          idempotency_key: "crawl-key-1",
        },
        fetchImpl,
      ),
    ).rejects.toThrow("forbidden");
  });
});

describe("fetchDocument", () => {
  it("returns notFound on 404 without reading a title", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ title: "SECRET TITLE", detail: "not_found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    const result = await fetchDocument(
      { accessToken: "jwt-token" },
      "33333333-3333-4333-8333-333333333333",
      fetchImpl,
    );
    expect(result).toEqual({ ok: false, notFound: true });
    expect(JSON.stringify(result)).not.toContain("SECRET");
  });
});

describe("inspectGraph client clamp", () => {
  it("sends depth 3 when the caller asked for 99", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          nodes: [{ object_id: "e1", object_type: "entity", chunk_id: "c", document_id: "d", version_id: "v", support: 1, hop: 1, title: "SECRET" }],
          locators: [],
          limitations: [{ code: "graph_acl_blindness", count: 7 }],
          row_count: 1,
          depth: 3,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const result = await inspectGraph(
      { accessToken: "jwt-token" },
      { entity_keys: ["e1"], depth: 99 },
      fetchImpl,
    );
    expect(JSON.parse(body).depth).toBe(3);
    expect(result.nodes[0]).not.toHaveProperty("title");
    expect(JSON.stringify(result.nodes[0])).not.toContain("SECRET");
    expect(result.limitations[0]?.count).toBe(7);
  });
});

describe("analyzeTable extra fields", () => {
  it("omits sql from the analyze POST body", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          table_id: "t",
          version_id: "v",
          document_id: "d",
          rows: [{ amount: 1 }, { amount: 2 }],
          source_ranges: ["A1:B2"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const result = await analyzeTable(
      { accessToken: "jwt-token" },
      {
        table_id: "11111111-1111-4111-8111-111111111111",
        version_id: "22222222-2222-4222-8222-222222222222",
        predicates: [{ column: "amount", operator: "gt", value: 0 }],
        sql: "select 1",
      } as never,
      fetchImpl,
    );
    expect(body).not.toContain("select 1");
    expect(result.rows).toHaveLength(2);
    expect(clientComputedTableTotal()).toBeNull();
  });
});

describe("GAP-07-14 no delete-document HTTP helper", () => {
  it("does not export a deleteDocument client", async () => {
    const api = await import("./api");
    expect("deleteDocument" in api).toBe(false);
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

describe("reserveUpload MFA", () => {
  it("throws mfa_required on 403 MFA required", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ detail: "MFA required" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    await expect(
      reserveUpload(
        { accessToken: "jwt-token" },
        1024,
        "idem-upload-1",
        fetchImpl,
      ),
    ).rejects.toThrow("mfa_required");
  });
});
