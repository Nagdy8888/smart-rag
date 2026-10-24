import { describe, expect, it, vi } from "vitest";
import { fetchUsageMe } from "./usage";

const auth = { accessToken: "test-only" };
const valid = { scope: "me", cost_usd: "0.000123", prompt_tokens: 123, completion_tokens: 45, usage_rows: 2 };
const response = (body: unknown) => vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(body), { status: 200 }));

describe("usage response integrity", () => {
  it("preserves the recorded cost without repricing and strips unrelated text", async () => {
    expect(await fetchUsageMe(auth, response({ ...valid, prompt_text: "PRIVATE" }))).toEqual(valid);
  });
  it.each([{}, { ...valid, cost_usd: null }, { ...valid, prompt_tokens: -1 }, { ...valid, usage_rows: "2" }, { ...valid, cost_usd: "NaN" }])("rejects malformed totals instead of inventing zeros", async (body) => {
    await expect(fetchUsageMe(auth, response(body))).rejects.toThrow("invalid_usage_response");
  });
  it("accepts actual zero usage", async () => {
    const empty = { scope: "me", cost_usd: 0, prompt_tokens: 0, completion_tokens: 0, usage_rows: 0 };
    expect(await fetchUsageMe(auth, response(empty))).toEqual(empty);
  });
});
