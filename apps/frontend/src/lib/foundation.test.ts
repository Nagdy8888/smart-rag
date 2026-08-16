import { describe, expect, it } from "vitest";
import { foundationCapability } from "./foundation";

describe("foundation capability", () => {
  it("does not claim retrieval or Stitch readiness", () => {
    expect(foundationCapability).toEqual({
      status: "thin_developer_ui",
      retrievalImplemented: false,
      stitchImplemented: false,
    });
  });
});
