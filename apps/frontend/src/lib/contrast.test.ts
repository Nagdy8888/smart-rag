import { describe, expect, it } from "vitest";
import { contrastRatio, relativeLuminance, WCAG_AA_NORMAL_TEXT } from "./contrast";
import {
  COLOR_ACCENT,
  COLOR_ACCENT_FG,
  COLOR_BG,
  COLOR_DANGER,
  COLOR_SURFACE,
  COLOR_PRIMARY,
  COLOR_PRIMARY_FG,
  COLOR_SURFACE_MUTED,
  COLOR_EVIDENCE,
  COLOR_EVIDENCE_MUTED,
  COLOR_TEXT,
  COLOR_TEXT_MUTED,
  COLOR_WARNING,
} from "./design-tokens";

describe("WCAG AA token contrast", () => {
  it("meets 4.5:1 for body, muted, accent, and danger pairs", () => {
    const pairs: Array<[string, string, string]> = [
      ["text on canvas", COLOR_TEXT, COLOR_BG],
      ["text on surface", COLOR_TEXT, COLOR_SURFACE],
      ["muted on surface", COLOR_TEXT_MUTED, COLOR_SURFACE],
      ["accent foreground", COLOR_ACCENT_FG, COLOR_ACCENT],
      ["danger on surface", COLOR_DANGER, COLOR_SURFACE],
      ["primary foreground", COLOR_PRIMARY_FG, COLOR_PRIMARY],
      ["accent on surface", COLOR_ACCENT, COLOR_SURFACE],
      ["accent on canvas", COLOR_ACCENT, COLOR_BG],
      ["muted on canvas", COLOR_TEXT_MUTED, COLOR_BG],
      ["muted on muted surface", COLOR_TEXT_MUTED, COLOR_SURFACE_MUTED],
      ["evidence marker text", COLOR_EVIDENCE, COLOR_EVIDENCE_MUTED],
      ["evidence on surface", COLOR_EVIDENCE, COLOR_SURFACE],
    ];
    for (const [label, fg, bg] of pairs) {
      expect(contrastRatio(fg, bg), label).toBeGreaterThanOrEqual(
        WCAG_AA_NORMAL_TEXT,
      );
    }
    expect(relativeLuminance(COLOR_SURFACE)).toBeGreaterThan(
      relativeLuminance(COLOR_TEXT),
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
