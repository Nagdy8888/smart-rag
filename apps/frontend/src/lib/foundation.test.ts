import { describe, expect, it } from "vitest";
import { foundationCapability } from "./foundation";

describe("foundation capability", () => {
  it("does not claim retrieval readiness without the API", () => {
    expect(foundationCapability).toEqual({
      status: "stitch_first_console",
      retrievalImplemented: false,
      stitchImplemented: true,
    });
  });
});
