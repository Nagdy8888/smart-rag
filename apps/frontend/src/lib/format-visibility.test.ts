// @vitest-environment node

import { describe, expect, it } from "vitest";
import { absentStatusLabel, formatVisibility } from "./format-visibility";

describe("formatVisibility", () => {
  it("maps company_visible to Company visible", () => {
    expect(formatVisibility("company_visible")).toBe("Company visible");
  });

  it("title-cases unknown snake_case values", () => {
    expect(formatVisibility("team_only")).toBe("Team only");
  });
});

describe("absentStatusLabel", () => {
  it("returns Not indexed or Pending", () => {
    expect(absentStatusLabel()).toBe("Not indexed");
    expect(absentStatusLabel("pending")).toBe("Pending");
  });
});
