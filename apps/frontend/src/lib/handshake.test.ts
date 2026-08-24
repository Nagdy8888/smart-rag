import { describe, expect, it, vi } from "vitest";
import {
  evaluatePaidHandshake,
  handshakeBelowMinCopy,
  isSseSchemaNewerThanCatalog,
  mayStartPaidPost,
  paidSendBlockReason,
  QUERY_NOT_READY_COPY,
} from "./handshake";
import { CLIENT_VERSION, clientVersionIsSupported } from "./client-version";

describe("client version handshake", () => {
  it("treats 0.1.0 as meeting the published minimum", () => {
    expect(clientVersionIsSupported(CLIENT_VERSION, "0.1.0")).toBe(true);
    expect(clientVersionIsSupported("0.0.9", "0.1.0")).toBe(false);
    expect(clientVersionIsSupported("9.0.0", "0.1.0")).toBe(true);
    expect(clientVersionIsSupported("", "0.1.0")).toBe(false);
    expect(clientVersionIsSupported("not-semver", "0.1.0")).toBe(false);
  });
});

describe("evaluatePaidHandshake", () => {
  const meta = {
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  };

  it("blocks send when the client is below min_client_version", () => {
    const decision = evaluatePaidHandshake(
      { ...meta, min_client_version: "9.0.0" },
      "ok",
      "0.1.0",
    );
    expect(decision.allowPaidPost).toBe(false);
    expect(decision.kind).toBe("below_min");
    expect(handshakeBelowMinCopy()).toBe(
      "This client is below min_client_version. Update before asking a question.",
    );
    expect(
      mayStartPaidPost(decision, { runId: null, terminal: null }),
    ).toBe(false);
  });

  it("fails closed for new paid POST when meta is unreachable", () => {
    const decision = evaluatePaidHandshake(null, "error");
    expect(decision.allowPaidPost).toBe(false);
    expect(decision.kind).toBe("unreachable");
  });

  it("continues when sse_schema_version is newer than the client catalog", () => {
    expect(isSseSchemaNewerThanCatalog("2", "1")).toBe(true);
    const decision = evaluatePaidHandshake(
      { ...meta, sse_schema_version: "2" },
      "ok",
      "0.1.0",
      "1",
    );
    expect(decision.allowPaidPost).toBe(true);
    expect(decision.kind).toBe("schema_newer");
  });

  it("allows resume GET when a run already exists even if POST is blocked", () => {
    const decision = evaluatePaidHandshake(
      { ...meta, min_client_version: "9.0.0" },
      "ok",
    );
    expect(
      mayStartPaidPost(decision, { runId: "run-1", terminal: null }),
    ).toBe(true);
  });
});

describe("google oauth guard", () => {
  it("does not invoke OAuth when the provider is disabled", async () => {
    const { maybeSignInWithGoogle, GOOGLE_OAUTH_ENABLED } = await import(
      "./auth/google"
    );
    const signInWithOAuth = vi.fn();
    const result = await maybeSignInWithGoogle(
      GOOGLE_OAUTH_ENABLED,
      signInWithOAuth,
    );
    expect(GOOGLE_OAUTH_ENABLED).toBe(false);
    expect(result.invoked).toBe(false);
    expect(signInWithOAuth).not.toHaveBeenCalled();
  });
});


describe("paidSendBlockReason", () => {
  const meta = {
    api_version: "1",
    sse_schema_version: "1",
    min_client_version: "0.1.0",
  };
  const ready = {
    status: "ok",
    query_ready: true,
    detail: "ok",
    rate_limit_degraded: false,
    dependencies: [{ name: "paradedb", status: "down" }],
  };

  it("blocks a new question when query_ready is false", () => {
    const decision = evaluatePaidHandshake(meta, "ok");
    expect(
      paidSendBlockReason(decision, { ...ready, query_ready: false }, {
        runId: null,
        terminal: null,
      }),
    ).toBe(QUERY_NOT_READY_COPY);
  });

  it("allows Hybrid when query_ready is true even if BM25 is down", () => {
    const decision = evaluatePaidHandshake(meta, "ok");
    expect(
      paidSendBlockReason(decision, ready, { runId: null, terminal: null }),
    ).toBeNull();
  });

  it("does not block resume of an in-flight run", () => {
    const decision = evaluatePaidHandshake(meta, "ok");
    expect(
      paidSendBlockReason(
        decision,
        { ...ready, query_ready: false },
        { runId: "run-1", terminal: null },
      ),
    ).toBeNull();
  });
});
