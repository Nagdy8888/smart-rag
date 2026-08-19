/**
 * Session query keys must not store the raw Bearer JWT.
 */

import { describe, expect, it } from "vitest";
import {
  sessionCacheScope,
  sessionQueryKeys,
} from "./query-keys";

/**
 * Build an unsigned compact JWT whose payload contains `sub`.
 *
 * @param sub - Auth user id.
 * @returns Compact JWT string.
 */
function jwtWithSub(sub: string): string {
  const header = globalThis.btoa(JSON.stringify({ alg: "none", typ: "JWT" }));
  const payload = globalThis.btoa(JSON.stringify({ sub }));
  return `${header}.${payload}.sig`;
}

describe("sessionCacheScope", () => {
  it("returns sub and never the raw token", () => {
    const token = jwtWithSub("11111111-1111-4111-8111-111111111111");
    expect(sessionCacheScope(token)).toBe(
      "11111111-1111-4111-8111-111111111111",
    );
    expect(sessionCacheScope(token)).not.toBe(token);
  });

  it("returns null when signed out", () => {
    expect(sessionCacheScope(null)).toBeNull();
    expect(sessionCacheScope("")).toBeNull();
  });

  it("does not echo a malformed token", () => {
    expect(sessionCacheScope("jwt-token")).toBe("invalid");
  });
});

describe("sessionQueryKeys", () => {
  it("keys on user id rather than the Bearer JWT", () => {
    const token = jwtWithSub("user-a");
    const keys = sessionQueryKeys(token);
    const serialized = JSON.stringify(keys);
    expect(serialized).not.toContain(token);
    expect(keys.me).toEqual(["me", "user-a"]);
    expect(keys.conversations).toEqual(["conversations", "user-a"]);
    expect(keys.consoleReady).toEqual(["console-ready", "user-a"]);
    expect(keys.citations("run-1")).toEqual(["citations", "user-a", "run-1"]);
  });

  it("isolates two users without sharing a token-shaped key", () => {
    const first = sessionQueryKeys(jwtWithSub("user-a"));
    const second = sessionQueryKeys(jwtWithSub("user-b"));
    expect(first.me).not.toEqual(second.me);
    expect(first.me[1]).toBe("user-a");
    expect(second.me[1]).toBe("user-b");
  });
});
