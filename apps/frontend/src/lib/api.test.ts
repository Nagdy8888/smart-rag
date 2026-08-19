import { describe, expect, it } from "vitest";
import {
  acceptInvitation,
  adminMutationHeaders,
  analyzeTable,
  approveEntityRule,
  classifyApiError,
  createInvitation,
  enableTool,
  enqueueWebsiteCrawl,
  fetchDocument,
  fetchReady,
  fetchOperatorReady,
  loadConsoleReadiness,
  fetchUsageCompany,
  finalizeUpload,
  importGlossary,
  inspectGraph,
  listCitations,
  listTools,
  offboardUser,
  paidMutationHeaders,
  reserveUpload,
  resumeHeaders,
  shouldResumeExistingRun,
  startMessageStream,
  startOrResumeMessageStream,
  cancelRun,
  deleteConversation,
  fetchMe,
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

  it("maps unknown 5xx to a generic server failure", () => {
    expect(
      classifyApiError(500, {
        detail: "Traceback (most recent call last): boom",
      }),
    ).toEqual({ kind: "server", status: 500 });
  });

  it("does not treat a traceback string as a safe detail code", () => {
    expect(
      classifyApiError(401, {
        detail: "Traceback (most recent call last): AuthApiError",
      }),
    ).toEqual({
      kind: "auth",
      status: 401,
      detail: "unauthorized",
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

  it("forwards AbortSignal to admit POST and resume GET", async () => {
    const controller = new AbortController();
    const signals: Array<AbortSignal | null | undefined> = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      signals.push(init?.signal);
      const url = String(input);
      if (url.includes("/messages")) {
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
      return new Response("event: schema\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    };
    await startMessageStream(
      { accessToken: "jwt-token" },
      "66666666-6666-4666-8666-666666666666",
      "hello",
      "33333333-3333-4333-8333-333333333333",
      fetchImpl,
      controller.signal,
    );
    expect(signals).toHaveLength(2);
    expect(signals[0]).toBe(controller.signal);
    expect(signals[1]).toBe(controller.signal);
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

  it("forwards AbortSignal on resume GET", async () => {
    const controller = new AbortController();
    let seen: unknown;
    const fetchImpl: typeof fetch = async (_input, init) => {
      seen = init?.signal;
      return new Response("event: heartbeat\ndata: {}\n\n", {
        status: 200,
        headers: { "Content-Type": "text/event-stream" },
      });
    };
    await startOrResumeMessageStream(
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
      controller.signal,
    );
    expect(seen).toBe(controller.signal);
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
    expect(result.source_ranges).toEqual(["A1:B2"]);
    expect(clientComputedTableTotal()).toBeNull();
  });
});

describe("GAP-07-14 no delete-document HTTP helper", () => {
  it("does not export a deleteDocument client", async () => {
    const api = await import("./api");
    expect("deleteDocument" in api).toBe(false);
  });
});

describe("administration clients", () => {
  function expectBearerOnly(headers: Record<string, string>): void {
    expect(headers.Authorization).toBe("Bearer jwt-token");
    expect(headers["X-Test-Role"]).toBeUndefined();
    expect(headers["X-Test-User-Id"]).toBeUndefined();
    expect(headers["X-Role"]).toBeUndefined();
    expect(Object.keys(headers).some((key) => /role/i.test(key))).toBe(false);
  }

  it("sends Bearer only on adminMutationHeaders even with a forged owner role", () => {
    const forgedRole = "owner";
    void forgedRole;
    const headers = adminMutationHeaders({ accessToken: "jwt-token" });
    expectBearerOnly(headers);
    expect(headers["X-Client-Version"]).toBeUndefined();
  });

  it("createInvitation posts extra-forbid body and classifies 403 forbidden", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      expectBearerOnly(init?.headers as Record<string, string>);
      return new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    };
    await expect(
      createInvitation(
        { accessToken: "jwt-token" },
        {
          email: "a@b.test",
          role: "member",
          upload_enabled: true,
          sql: "drop table profiles",
        } as never,
        fetchImpl,
      ),
    ).rejects.toThrow("forbidden");
    expect(JSON.parse(body)).toEqual({
      email: "a@b.test",
      role: "member",
      upload_enabled: true,
    });
    expect(body).not.toContain("drop table");
  });

  it("createInvitation classifies MFA required, 402, and 429", async () => {
    const cases: Array<{
      status: number;
      detail: string;
      thrown: string;
      headers?: Record<string, string>;
    }> = [
      { status: 403, detail: "MFA required", thrown: "mfa_required" },
      { status: 402, detail: "budget_exhausted", thrown: "budget_exhausted" },
      {
        status: 429,
        detail: "rate_limited",
        thrown: "rate_limited",
        headers: { "Retry-After": "12" },
      },
    ];
    for (const item of cases) {
      const fetchImpl: typeof fetch = async () =>
        new Response(JSON.stringify({ detail: item.detail }), {
          status: item.status,
          headers: {
            "Content-Type": "application/json",
            ...(item.headers ?? {}),
          },
        });
      await expect(
        createInvitation(
          { accessToken: "jwt-token" },
          { email: "a@b.test", role: "member", upload_enabled: false },
          fetchImpl,
        ),
      ).rejects.toThrow(item.thrown);
    }
  });

  it("offboardUser still posts with Bearer only for a member helper call", async () => {
    const fetchImpl: typeof fetch = async (_input, init) => {
      expectBearerOnly(init?.headers as Record<string, string>);
      expect(String(_input)).toContain(
        "/admin/users/33333333-3333-4333-8333-333333333333/offboard",
      );
      return new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    };
    await expect(
      offboardUser(
        { accessToken: "jwt-token" },
        "33333333-3333-4333-8333-333333333333",
        fetchImpl,
      ),
    ).rejects.toThrow("forbidden");
  });

  it("enableTool still posts { active } with Bearer only", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      expectBearerOnly(init?.headers as Record<string, string>);
      return new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    };
    await expect(
      enableTool({ accessToken: "jwt-token" }, "export_csv", false, fetchImpl),
    ).rejects.toThrow("forbidden");
    expect(JSON.parse(body)).toEqual({ active: false });
  });

  it("fetchUsageCompany 403s for a member", async () => {
    const fetchImpl: typeof fetch = async (_input, init) => {
      expectBearerOnly(init?.headers as Record<string, string>);
      return new Response(JSON.stringify({ detail: "forbidden" }), {
        status: 403,
        headers: { "Content-Type": "application/json" },
      });
    };
    await expect(
      fetchUsageCompany({ accessToken: "jwt-token" }, fetchImpl),
    ).rejects.toThrow("forbidden");
  });

  it("omits unauthorized tool names from the catalog fixture", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(
        JSON.stringify([
          {
            tool_key: "export_csv",
            version_label: "1",
            short_name: "CSV export",
            purpose: "Export rows",
            required_role: "member",
            risk_class: "low",
            active: true,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    const cards = await listTools({ accessToken: "jwt-token" }, undefined, fetchImpl);
    expect(cards.map((card) => card.tool_key)).toEqual(["export_csv"]);
    expect(JSON.stringify(cards)).not.toContain("admin_secret_tool");
    expect(JSON.stringify(cards)).not.toContain("REDACTED");
  });

  it("approveEntityRule posts { row_version } only", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      expectBearerOnly(init?.headers as Record<string, string>);
      return new Response(
        JSON.stringify({
          rule_id: "rule-1",
          status: "approved",
          row_version: 4,
          entity_rules_generation: 2,
          rebuild_job_id: null,
          repair_job_id: null,
          invalidated: true,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const result = await approveEntityRule(
      { accessToken: "jwt-token" },
      "rule-1",
      3,
      fetchImpl,
    );
    expect(JSON.parse(body)).toEqual({ row_version: 3 });
    expect(result.status).toBe("approved");
  });

  it("importGlossary omits SQL-like extra fields", async () => {
    let body = "";
    const fetchImpl: typeof fetch = async (_input, init) => {
      body = String(init?.body ?? "");
      return new Response(
        JSON.stringify({
          import_id: "imp-1",
          status: "pending_approval",
          entry_count: 1,
          alias_count: 0,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    };
    await importGlossary(
      { accessToken: "jwt-token" },
      {
        source_name: "sme",
        source_version: "1",
        idempotency_key: "idem-gloss-1",
        sql: "select * from app.search_aliases",
        entries: [
          {
            entry_key: "INV.1",
            canonical_term: "Invoice",
            language: "en",
            entry_type: "canonical_term",
            effective_scope: "company",
            sql: "delete from aliases",
          },
        ],
      } as never,
      fetchImpl,
    );
    const parsed = JSON.parse(body) as Record<string, unknown>;
    expect(parsed).not.toHaveProperty("sql");
    expect(body).not.toContain("select *");
    expect(body).not.toContain("delete from");
    expect(parsed.source_name).toBe("sme");
    expect(Array.isArray(parsed.entries)).toBe(true);
  });

  it("createInvitation omits raw_token even when the JSON leaks it", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          invitation_id: "inv-1",
          email: "<img src=x onerror=alert(1)>@evil.test",
          role: "member",
          upload_enabled: false,
          expires_at: "2026-08-18T00:00:00Z",
          raw_token: "once-secret",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      );
    const created = await createInvitation(
      { accessToken: "jwt-token" },
      { email: "a@b.test", role: "member", upload_enabled: false },
      fetchImpl,
    );
    expect(created).not.toHaveProperty("raw_token");
    expect(created.invitation_id).toBe("inv-1");
    expect(created.email).toContain("<img");
  });
});

describe("fetchReady", () => {
  it("maps public GET /health/ready without named dependencies", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(
        JSON.stringify({
          status: "degraded",
          query_ready: false,
          detail: "not_query_ready",
          dependencies: [
            { name: "paradedb", status: "down" },
            { name: "lightrag", status: "unconfigured" },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    const ready = await fetchReady(fetchImpl);
    expect(ready?.query_ready).toBe(false);
    expect(ready?.detail).toBe("not_query_ready");
    expect(ready?.dependencies).toEqual([]);
  });
});

describe("fetchOperatorReady", () => {
  it("maps GET /ops/ready named probes for owner/admin", async () => {
    const fetchImpl: typeof fetch = async (input, init) => {
      expect(String(input)).toContain("/ops/ready");
      expect((init?.headers as Record<string, string>).Authorization).toBe(
        "Bearer jwt-token",
      );
      return new Response(
        JSON.stringify({
          status: "degraded",
          query_ready: false,
          detail: "mock",
          rate_limit_degraded: false,
          dependencies: [{ name: "paradedb", status: "down" }],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const ready = await fetchOperatorReady({ accessToken: "jwt-token" }, fetchImpl);
    expect(ready?.dependencies).toEqual([{ name: "paradedb", status: "down" }]);
  });

  it("returns null on 403", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ detail: "forbidden" }), { status: 403 });
    await expect(
      fetchOperatorReady({ accessToken: "jwt-token" }, fetchImpl),
    ).resolves.toBeNull();
  });
});

describe("loadConsoleReadiness", () => {
  it("merges operator probes onto the public body", async () => {
    const fetchImpl: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes("/ops/ready")) {
        return new Response(
          JSON.stringify({
            status: "degraded",
            query_ready: false,
            detail: "mock",
            rate_limit_degraded: true,
            dependencies: [{ name: "paradedb", status: "down" }],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        );
      }
      return new Response(
        JSON.stringify({
          status: "degraded",
          query_ready: false,
          detail: "not_query_ready",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    };
    const ready = await loadConsoleReadiness({ accessToken: "jwt-token" }, fetchImpl);
    expect(ready?.dependencies).toEqual([{ name: "paradedb", status: "down" }]);
    expect(ready?.rate_limit_degraded).toBe(true);
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

  it("does not return a reservation on 402 quota or budget exhaustion", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ detail: "budget_exhausted", signed_url: "https://secret" }), {
        status: 402,
        headers: { "Content-Type": "application/json" },
      });
    await expect(
      reserveUpload(
        { accessToken: "jwt-token" },
        1024,
        "idem-upload-2",
        fetchImpl,
      ),
    ).rejects.toThrow("upload_reserve_failed");
  });
});

describe("fetchMe session revocation", () => {
  it("throws session_revoked on 401 session_revoked", async () => {
    const fetchImpl: typeof fetch = async (_input, init) => {
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Test-Role"]).toBeUndefined();
      return new Response(JSON.stringify({ detail: "session_revoked" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    };
    await expect(fetchMe({ accessToken: "jwt-token" }, fetchImpl)).rejects.toThrow(
      "session_revoked",
    );
  });
});

describe("paid POST handshake 426", () => {
  it("classifies upgrade and does not open the SSE GET", async () => {
    const calls: string[] = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      return new Response(
        JSON.stringify({
          min_client_version: "9.0.0",
          sse_schema_version: "1",
        }),
        { status: 426, headers: { "Content-Type": "application/json" } },
      );
    };
    const started = await startMessageStream(
      { accessToken: "jwt-token" },
      "conv-1",
      "hello",
      "33333333-3333-4333-8333-333333333333",
      fetchImpl,
    );
    expect(started.failure).toEqual({
      kind: "upgrade",
      minClientVersion: "9.0.0",
      sseSchemaVersion: "1",
    });
    expect(calls).toHaveLength(1);
    expect(calls[0]?.startsWith("POST")).toBe(true);
    expect(calls.some((call) => call.includes("/events"))).toBe(false);
  });
});

describe("private-run resume 404", () => {
  it("classifies a foreign or missing run as deleted without a second POST", async () => {
    const calls: string[] = [];
    const fetchImpl: typeof fetch = async (input, init) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      calls.push(`${method} ${url}`);
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Client-Version"]).toBeUndefined();
      return new Response(JSON.stringify({ detail: "not_found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    };
    const started = await startOrResumeMessageStream(
      { accessToken: "jwt-token" },
      "conv-1",
      "retry",
      {
        runId: "run-foreign",
        terminal: null,
        lastSequence: 3,
        idempotencyKey: "33333333-3333-4333-8333-333333333333",
      },
      fetchImpl,
    );
    expect(started.resumed).toBe(true);
    expect(started.failure).toEqual({ kind: "deleted" });
    expect(calls).toEqual([
      "GET http://127.0.0.1:8000/runs/run-foreign/events?after=3",
    ]);
    expect(calls.some((call) => call.startsWith("POST"))).toBe(false);
  });
});

describe("cancelRun", () => {
  it("posts cancel with resume headers and no X-Client-Version", async () => {
    const fetchImpl: typeof fetch = async (input, init) => {
      expect(String(input)).toBe("http://127.0.0.1:8000/runs/run-1/cancel");
      expect(init?.method).toBe("POST");
      const headers = init?.headers as Record<string, string>;
      expect(headers.Authorization).toBe("Bearer jwt-token");
      expect(headers["X-Client-Version"]).toBeUndefined();
      expect(headers["X-Test-Role"]).toBeUndefined();
      return new Response(null, { status: 204 });
    };
    await expect(
      cancelRun({ accessToken: "jwt-token" }, "run-1", fetchImpl),
    ).resolves.toBe(true);
  });
});

describe("deleteConversation", () => {
  it("DELETEs the conversation and treats 204 as success", async () => {
    const fetchImpl: typeof fetch = async (input, init) => {
      expect(String(input)).toBe(
        "http://127.0.0.1:8000/conversations/conv-1",
      );
      expect(init?.method).toBe("DELETE");
      const headers = init?.headers as Record<string, string>;
      expect(headers["X-Client-Version"]).toBeUndefined();
      return new Response(null, { status: 204 });
    };
    await expect(
      deleteConversation({ accessToken: "jwt-token" }, "conv-1", fetchImpl),
    ).resolves.toBe(true);
  });
});

describe("listCitations without snippets", () => {
  it("keeps ids and drops passage snippet fields", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(
        JSON.stringify([
          {
            citation_id: "cite-1",
            citation_index: 1,
            chunk_id: "chunk-1",
            snippet: "SECRET PASSAGE",
            passage: "SECRET PASSAGE",
            provenance: {
              page_number: 3,
              snippet: "SECRET PASSAGE",
              url: "https://example.com/doc",
            },
            source_unavailable: false,
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    const citations = await listCitations(
      { accessToken: "jwt-token" },
      "run-1",
      fetchImpl,
    );
    expect(citations).toEqual([
      {
        citation_id: "cite-1",
        citation_index: 1,
        chunk_id: "chunk-1",
        provenance: { page_number: 3, url: "https://example.com/doc" },
        source_unavailable: false,
      },
    ]);
    expect(JSON.stringify(citations)).not.toContain("SECRET");
    expect(JSON.stringify(citations)).not.toContain("snippet");
  });

  it("returns an empty list for a 404 private run", async () => {
    const fetchImpl: typeof fetch = async () =>
      new Response(JSON.stringify({ snippet: "SECRET" }), { status: 404 });
    const citations = await listCitations(
      { accessToken: "jwt-token" },
      "run-missing",
      fetchImpl,
    );
    expect(citations).toEqual([]);
  });
});
