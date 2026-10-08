import { describe, expect, it } from "vitest";
import { contrastRatio, relativeLuminance, WCAG_AA_NORMAL_TEXT } from "./contrast";
import {
  COLOR_ACCENT,
  COLOR_ACCENT_FG,
  COLOR_DANGER,
  COLOR_SURFACE,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FG,
  COLOR_SURFACE_MUTED,
  COLOR_EVIDENCE,
  COLOR_FIELD,
  COLOR_FIELD_FG,
  COLOR_TEXT,
  COLOR_TEXT_MUTED,
  COLOR_WARNING,
} from "./design-tokens";

describe("WCAG AA token contrast", () => {
  it("meets 4.5:1 for canvas, surface, accent, and evidence pairs", () => {
    const pairs: Array<[string, string, string]> = [
      ["field text on field", COLOR_FIELD_FG, COLOR_FIELD],
      ["text on plate", COLOR_TEXT, COLOR_SURFACE],
      ["muted on plate", COLOR_TEXT_MUTED, COLOR_SURFACE],
      ["accent foreground on electric", COLOR_ACCENT_FG, COLOR_ACCENT],
      ["danger on plate", COLOR_DANGER, COLOR_SURFACE],
      ["primary foreground", COLOR_PRIMARY_FG, COLOR_PRIMARY],
      ["muted on muted plate", COLOR_TEXT_MUTED, COLOR_SURFACE_MUTED],
      ["evidence chip text", COLOR_ACCENT_FG, COLOR_EVIDENCE],
    ];
    for (const [label, fg, bg] of pairs) {
      expect(contrastRatio(fg, bg), label).toBeGreaterThanOrEqual(
        WCAG_AA_NORMAL_TEXT,
      );
    }
    expect(relativeLuminance(COLOR_SURFACE)).toBeGreaterThan(
      relativeLuminance(COLOR_TEXT),
    );
    expect(relativeLuminance(COLOR_FIELD)).toBeGreaterThan(
      relativeLuminance(COLOR_FIELD_FG),
    );
  });

  it("does not treat warning hex as the only body-text color", () => {
    const warningOnWhite = contrastRatio(COLOR_WARNING, COLOR_SURFACE);
    expect(warningOnWhite).toBeGreaterThan(3);
    expect(COLOR_WARNING).toBe("#A16207");
    expect(contrastRatio(COLOR_TEXT, COLOR_SURFACE)).toBeGreaterThanOrEqual(
      WCAG_AA_NORMAL_TEXT,
    );
  });
});
