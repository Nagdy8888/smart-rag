/**
 * Cross-cutting quality audit: overflow, computed geometry, unmapped actions,
 * and unresolved GAP copy. Login is deterministic; signed-in routes skip when
 * FastAPI is down.
 */

import { expect, test, type Page } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1280, height: 800 },
] as const;

const ALLOWED_UNMAPPED_NAMES = new Set([
  "Cancel",
  "Close",
  "Hide password",
  "Show password",
]);

/**
 * Return page-level horizontal overflow in CSS pixels.
 *
 * @param page - Playwright page.
 * @returns Positive overflow, or 0.
 */
async function horizontalOverflow(page: Page): Promise<number> {
  return page.evaluate(() => {
    const root = document.documentElement;
    return Math.max(0, root.scrollWidth - window.innerWidth);
  });
}

/**
 * Collect visible unlabeled or unmapped actionable controls.
 *
 * @param page - Playwright page.
 * @returns Failure strings.
 */
async function unmappedVisibleActions(page: Page): Promise<string[]> {
  return page.evaluate((allowed) => {
    const allowedNames = new Set(allowed);
    const nodes = Array.from(
      document.querySelectorAll<HTMLElement>(
        'button, a[href], [role="tab"], [role="menuitem"]',
      ),
    );
    const failures: string[] = [];
    for (const node of nodes) {
      const style = window.getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden") {
        continue;
      }
      const href = node.getAttribute("href");
      if (href === "#") {
        failures.push("empty hash href");
      }
      const name = (
        node.getAttribute("aria-label") ||
        node.textContent ||
        ""
      )
        .replace(/\s+/g, " ")
        .trim();
      if (name === "") {
        failures.push("unnamed control");
        continue;
      }
      if (allowedNames.has(name)) {
        continue;
      }
      if (!node.getAttribute("data-action-id")) {
        failures.push(`unmapped visible action: ${name}`);
      }
    }
    return failures;
  }, [...ALLOWED_UNMAPPED_NAMES]);
}

test("login geometry, overflow, and mapped Sign in at required viewports", async ({
  page,
}) => {
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    expect(await horizontalOverflow(page)).toBe(0);
    await expect(page.getByRole("heading", { name: "Unavailable" })).toHaveCount(0);
    await expect(page.getByText(/GAP-07-/)).toHaveCount(0);
    const signIn = page.getByRole("button", { name: "Sign in" });
    await expect(signIn).toHaveAttribute("data-action-id", "auth.sign_in");
    const box = await signIn.evaluate((element) => {
      const style = getComputedStyle(element);
      return {
        height: Math.round(element.getBoundingClientRect().height),
        radius: style.borderRadius,
      };
    });
    expect(box.height).toBe(40);
    expect(box.radius).toBe("8px");
    const email = page.getByLabel("Email");
    const inputHeight = await email.evaluate((element) =>
      Math.round(element.getBoundingClientRect().height),
    );
    expect(inputHeight).toBe(40);
    const skip = page.getByRole("link", { name: "Skip to main content" });
    await expect(skip).toHaveAttribute("data-action-id", "shell.skip");
  }
});

test("authenticated Ask has no page overflow or GAP chrome when signed in", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.locator("#main")).toBeVisible();
    expect(await horizontalOverflow(page)).toBeLessThanOrEqual(1);
    await expect(page.getByRole("heading", { name: "Unavailable" })).toHaveCount(0);
    await expect(page.locator("a[href='#']")).toHaveCount(0);
    const unmapped = await unmappedVisibleActions(page);
    const unexpected = unmapped.filter(
      (item) =>
        !item.startsWith("unmapped visible action: Sessions") &&
        !item.startsWith("unmapped visible action: Menu") &&
        !item.startsWith("unmapped visible action: Actions"),
    );
    expect(unexpected).toEqual([]);
  }
});
