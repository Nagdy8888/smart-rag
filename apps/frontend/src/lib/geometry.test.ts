/**
 * CSS-source geometry lock. jsdom does not apply CSS modules, so these
 * tests parse the stylesheets the browser will load.
 */

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CONTROL_HEIGHT,
  NAV_WIDTH,
  RADIUS_MD,
  RADIUS_SM,
  ROW_HEIGHT,
  TEXT_BODY_SIZE,
  TEXT_PAGE_TITLE_SIZE,
  TOPBAR_HEIGHT,
} from "./design-tokens";

const here = path.dirname(fileURLToPath(import.meta.url));
const globals = readFileSync(path.join(here, "../app/globals.css"), "utf8");
const ui = readFileSync(path.join(here, "../components/ui/ui.module.css"), "utf8");
const shell = readFileSync(
  path.join(here, "../components/ui/app-shell.module.css"),
  "utf8",
);

describe("primitive geometry source lock", () => {
  it("keeps 40px controls, 8px control radius, 12px cards, 48px rows, and 2px/2px focus", () => {
    expect(CONTROL_HEIGHT).toBe("40px");
    expect(RADIUS_SM).toBe("8px");
    expect(RADIUS_MD).toBe("12px");
    expect(ROW_HEIGHT).toBe("48px");
    expect(TEXT_PAGE_TITLE_SIZE).toBe("24px");
    expect(TEXT_BODY_SIZE).toBe("14px");
    expect(NAV_WIDTH).toBe("232px");
    expect(TOPBAR_HEIGHT).toBe("56px");
    expect(globals).toMatch(/--control-height:\s*40px;/);
    expect(globals).toMatch(/--radius-sm:\s*8px;/);
    expect(globals).toMatch(/--radius-md:\s*12px;/);
    expect(globals).toMatch(/--row-height:\s*48px;/);
    expect(globals).toMatch(/--nav-width:\s*232px;/);
    expect(globals).toMatch(/--topbar-height:\s*56px;/);
    expect(globals).toMatch(/--text-page-title-size:\s*24px;/);
    expect(globals).toMatch(/outline:\s*2px\s+solid\s+var\(--color-focus\)/);
    expect(globals).toMatch(/outline-offset:\s*2px/);
    expect(ui).toMatch(/\.button\s*\{[\s\S]*?height:\s*var\(--control-height\)/);
    expect(ui).toMatch(/\.control\s*\{[\s\S]*?height:\s*var\(--control-height\)/);
    expect(ui).toMatch(/\.button\s*\{[\s\S]*?border-radius:\s*var\(--radius-sm\)/);
    expect(ui).toMatch(/\.pill\s*\{[\s\S]*?height:\s*24px/);
    expect(ui).toMatch(/\.confirmPanel\s*\{[\s\S]*?border-radius:\s*var\(--radius-lg\)/);
    expect(ui).toMatch(/\.table th,\s*\n\.table td\s*\{[\s\S]*?height:\s*var\(--row-height\)/);
    expect(shell).toMatch(/width:\s*var\(--nav-width\)/);
    expect(shell).toMatch(/min-height:\s*var\(--topbar-height\)/);
    expect(ui).toMatch(/text-transform:\s*none/);
    expect(globals).toMatch(/"Inter"/);
    expect(globals).not.toMatch(/backdrop-filter/i);
    expect(globals).not.toMatch(/\bblur\(/);
    expect(ui).not.toMatch(/backdrop-filter/i);
    expect(ui).not.toMatch(/\bblur\(/);
    expect(globals).not.toMatch(/fonts\.googleapis\.com/);
    expect(ui).not.toMatch(/fonts\.googleapis\.com/);
  });

  it("does not declare a second hex palette in primitive CSS", () => {
    expect(ui).not.toMatch(/#4E5BD5/i);
    expect(ui).not.toMatch(/#F4F6F8/i);
    expect(ui.split(".srOnly {").length).toBe(2);
  });
});
