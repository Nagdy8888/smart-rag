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

/**
 * Join CSS module sources so geometry locks survive owner splits.
 *
 * @param relativePaths - Paths under `apps/frontend/src`.
 * @returns Concatenated file text.
 */
function readCss(...relativePaths: string[]): string {
  return relativePaths
    .map((relative) => readFileSync(path.join(here, relative), "utf8"))
    .join("\n");
}

const globals = readFileSync(path.join(here, "../app/globals.css"), "utf8");
const ui = readCss(
  "../components/ui/ui.module.css",
  "../components/ui/styles/controls.module.css",
  "../components/ui/styles/data-display.module.css",
  "../components/ui/styles/overlays.module.css",
);
const shell = readCss(
  "../components/ui/app-shell.module.css",
  "../components/ui/app-nav.module.css",
  "../components/ui/app-topbar.module.css",
);
const chat = readCss(
  "../components/chat/chat.module.css",
  "../components/chat/chat-rail.module.css",
  "../components/chat/chat-transcript.module.css",
  "../components/chat/chat-composer.module.css",
  "../components/chat/run-progress-timeline.module.css",
);

describe("primitive geometry source lock", () => {
  it("keeps 40px controls, 10px control radius, 14px cards, 48px rows, and 2px focus", () => {
    expect(CONTROL_HEIGHT).toBe("40px");
    expect(RADIUS_SM).toBe("10px");
    expect(RADIUS_MD).toBe("14px");
    expect(ROW_HEIGHT).toBe("48px");
    expect(TEXT_PAGE_TITLE_SIZE).toBe("24px");
    expect(TEXT_BODY_SIZE).toBe("14px");
    expect(NAV_WIDTH).toBe("232px");
    expect(TOPBAR_HEIGHT).toBe("56px");
    expect(globals).toMatch(/--control-height:\s*40px;/);
    expect(globals).toMatch(/--radius-sm:\s*10px;/);
    expect(globals).toMatch(/--radius-md:\s*14px;/);
    expect(globals).toMatch(/--row-height:\s*48px;/);
    expect(globals).toMatch(/--nav-width:\s*232px;/);
    expect(globals).toMatch(/--topbar-height:\s*56px;/);
    expect(globals).toMatch(/--text-page-title-size:\s*24px;/);
    expect(globals).toMatch(/outline:\s*2px\s+solid\s+var\(--color-focus\)/);
    expect(globals).toMatch(/outline-offset:\s*2px/);
    expect(ui).toMatch(/\.button\s*\{[\s\S]*?height:\s*var\(--control-height\)/);
    expect(ui).toMatch(/\.control\s*\{[\s\S]*?height:\s*var\(--control-height\)/);
    expect(ui).toMatch(/\.button\s*\{[\s\S]*?border-radius:\s*var\(--radius-control\)/);
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

  it("keeps Windows and Edge on the light Inter stack without UA chrome", () => {
    expect(globals).toMatch(/color-scheme:\s*only light/);
    expect(globals).not.toMatch(/-webkit-font-smoothing:\s*antialiased/);
    expect(globals).not.toMatch(/-moz-osx-font-smoothing:\s*grayscale/);
    expect(globals).toMatch(/font-synthesis:\s*none/);
    expect(globals).toMatch(/appearance:\s*none/);
    expect(globals).not.toMatch(/max-width:\s*100vw/);
    expect(ui).toMatch(/\.button\s*\{[\s\S]*?appearance:\s*none/);
    expect(ui).toMatch(/\.control\s*\{[\s\S]*?appearance:\s*none/);
    expect(shell).toMatch(/\.shell\s*\{[\s\S]*?height:\s*100vh/);
    expect(chat).toMatch(/\.conversationButton\s*\{[\s\S]*?appearance:\s*none/);
    expect(ui).toMatch(/\.rovingList\s*\{[\s\S]*?display:\s*block/);
    expect(ui).toMatch(/\.rovingList > li\s*\{[\s\S]*?flex-shrink:\s*0/);
    expect(chat).toMatch(/\.railList > li\s*\{[^}]*flex-shrink:\s*0/);
    expect(chat).toMatch(/\.conversationButton\s*\{[\s\S]*?min-height:\s*56px/);
    expect(chat).toMatch(/\.conversationTitle\s*\{[\s\S]*?line-height:\s*20px/);
    expect(chat).toMatch(/\.conversationTime\s*\{[\s\S]*?line-height:\s*16px/);
    expect(chat).not.toMatch(/\.railList > li\s*\{[^}]*min-height:\s*0/);
  });

  it("does not declare a second hex palette in primitive CSS", () => {
    expect(ui).not.toMatch(/#4E5BD5/i);
    expect(ui).not.toMatch(/#F4F6F8/i);
    expect(ui.split(".srOnly {").length).toBe(2);
  });
});

describe("Ask independent scroll source lock", () => {
  it("bounds the shell and splits Sessions list from conversation overflow", () => {
    expect(shell).toMatch(/\.shell\s*\{[\s\S]*?height:\s*100dvh/);
    expect(shell).toMatch(/\.main\s*\{[\s\S]*?overflow-y:\s*auto/);
    expect(chat).toMatch(/\.page\s*\{[\s\S]*?overflow:\s*hidden/);
    expect(chat).toMatch(/\.railList\s*\{[\s\S]*?overflow-y:\s*auto/);
    expect(chat).toMatch(/\.conversation\s*\{[\s\S]*?overflow-y:\s*auto/);
    expect(chat).toMatch(/\.composer\s*\{[\s\S]*?flex-shrink:\s*0/);
    expect(chat).not.toMatch(/\.answer\s*\{[\s\S]*?overflow:\s*auto/);
    expect(chat).not.toMatch(/\.stage\s*\{[\s\S]*?max-width:\s*880px/);
    expect(chat).toMatch(/\.composer\s*\{[\s\S]*?width:\s*100%/);
    expect(chat).toMatch(/\.railBody\[hidden\]\s*\{[\s\S]*?display:\s*none/);
    expect(chat).toMatch(/\.workspaceSessionsExpanded\s*\{[\s\S]*?280px/);
    expect(ui).toMatch(/\.fieldFull\s*\{[\s\S]*?max-width:\s*none/);
    expect(shell).toMatch(/\.navIsCollapsed\s*\{[\s\S]*?width:\s*var\(--nav-width-collapsed\)/);
    expect(shell).not.toMatch(/@media \(min-width: 1280px\)/);
  });
});
