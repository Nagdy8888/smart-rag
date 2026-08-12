import { describe, expect, it } from "vitest";
import { foundationCapability } from "./foundation";

describe("foundation capability", () => {
  it("does not claim retrieval readiness", () => {
    expect(foundationCapability).toEqual({
      status: "unconfigured",
      retrievalImplemented: false,
    });
  });
});
