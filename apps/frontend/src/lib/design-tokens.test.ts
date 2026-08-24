/**
 * Token source of truth: visual contract, CSS `:root`, and the TS module match.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  COLOR_ACCENT,
  COLOR_BG,
  CONTROL_HEIGHT,
  DESIGN_TOKENS,
  RADIUS_MD,
  RADIUS_SM,
} from "./design-tokens";

const here = path.dirname(fileURLToPath(import.meta.url));
const cssPath = path.join(here, "../app/globals.css");

/**
 * Parse `:root` custom properties from `globals.css`.
 *
 * @param css - Stylesheet text.
 * @returns Property name to raw value.
 */
function parseRootTokens(css: string): Record<string, string> {
  const block = css.match(/:root\s*\{([\s\S]*?)\n\}/);
  if (block === null) {
    throw new Error("globals.css is missing a :root token block");
  }
  const tokens: Record<string, string> = {};
  for (const line of block[1].split("\n")) {
    const match = line.trim().match(/^(--[a-z0-9-]+):\s*(.+);$/);
    if (match !== null && match[1] !== undefined && match[2] !== undefined) {
      tokens[match[1]] = match[2].trim();
    }
  }
  return tokens;
}

describe("design token source of truth", () => {
  const css = readFileSync(cssPath, "utf8");
  const root = parseRootTokens(css);

  it("matches the Phase 8 visual-contract palette in CSS and TS", () => {
    for (const [name, value] of Object.entries(DESIGN_TOKENS)) {
      expect(root[name], name).toBe(value);
    }
    expect(COLOR_BG).toBe("#F4F6F8");
    expect(COLOR_ACCENT).toBe("#4E5BD5");
    expect(RADIUS_SM).toBe("8px");
    expect(RADIUS_MD).toBe("12px");
    expect(CONTROL_HEIGHT).toBe("40px");
  });

  it("rejects DESIGN.md YAML, teal canvas/accent, and blur", () => {
    const assigned = Object.values(root).join("\n").toLowerCase();
    expect(assigned).not.toContain("#004ac6");
    expect(assigned).not.toContain("#faf8ff");
    expect(root["--color-bg"]).not.toBe("#0F766E");
    expect(root["--color-accent"]).not.toBe("#0F766E");
    expect(root["--radius-md"]).not.toBe("8px");
    expect(css).not.toMatch(/backdrop-filter/i);
    expect(css).not.toMatch(/\bblur\(/);
    expect(css).not.toContain("cdn.tailwindcss.com");
    expect(css).not.toContain("fonts.googleapis.com");
  });

  it("maps tokens into Tailwind @theme without a second hex table", () => {
    expect(css).toContain('@import "tailwindcss"');
    expect(css).toContain("--color-page: var(--color-bg)");
    expect(css).toContain("--color-brand: var(--color-accent)");
    expect(css).toContain("--spacing: var(--space)");
    expect(css).not.toContain("tailwind.config");
  });
});
