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
    expect(box.radius).toBe("6px");
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
        !item.startsWith("unmapped visible action: Actions") &&
        !item.startsWith("unmapped visible action: Conversation actions"),
    );
    expect(unexpected).toEqual([]);
  }
});

type AskScrollProbe = {
  conversationCanScroll: boolean;
  sessionsVisible: boolean;
  sessionsCanScroll: boolean;
  afterConversation: {
    conversation: number;
    sessions: number;
    main: number;
    pageY: number;
  };
  afterSessions: {
    conversation: number;
    sessions: number;
    main: number;
    pageY: number;
  } | null;
};

/**
 * Force overflow in the Ask panes and measure independent scroll.
 *
 * @param page - Playwright page on `/`.
 * @returns Scroll measurements after injecting tall probes.
 */
async function measureAskScrollIndependence(page: Page): Promise<AskScrollProbe> {
  return page.evaluate(() => {
    const isVisible = (node: Element | null): node is HTMLElement => {
      if (!(node instanceof HTMLElement)) {
        return false;
      }
      const style = getComputedStyle(node);
      if (style.display === "none" || style.visibility === "hidden") {
        return false;
      }
      return node.getClientRects().length > 0;
    };

    const conversation = document.querySelector('[aria-label="Conversation"]');
    if (!(conversation instanceof HTMLElement)) {
      throw new Error("Conversation region is missing");
    }
    const sessions =
      Array.from(
        document.querySelectorAll('[role="listbox"][aria-label="Sessions"]'),
      ).find(isVisible) ?? null;
    const main = document.getElementById("main");

    if (conversation.querySelector('[data-scroll-probe="conversation"]') === null) {
      const filler = document.createElement("div");
      filler.dataset.scrollProbe = "conversation";
      filler.setAttribute("aria-hidden", "true");
      filler.style.minHeight = "2400px";
      filler.style.flexShrink = "0";
      conversation.appendChild(filler);
    }
    if (
      sessions !== null &&
      sessions.querySelector('[data-scroll-probe="sessions"]') === null
    ) {
      const filler = document.createElement("li");
      filler.dataset.scrollProbe = "sessions";
      filler.setAttribute("aria-hidden", "true");
      filler.style.minHeight = "2400px";
      filler.style.flexShrink = "0";
      sessions.appendChild(filler);
    }

    conversation.scrollTop = 0;
    if (sessions !== null) {
      sessions.scrollTop = 0;
    }
    if (main instanceof HTMLElement) {
      main.scrollTop = 0;
    }
    window.scrollTo(0, 0);

    conversation.scrollTop = 240;
    const afterConversation = {
      conversation: conversation.scrollTop,
      sessions: sessions?.scrollTop ?? 0,
      main: main instanceof HTMLElement ? main.scrollTop : 0,
      pageY: window.scrollY,
    };

    let afterSessions: AskScrollProbe["afterSessions"] = null;
    if (sessions !== null) {
      sessions.scrollTop = 240;
      afterSessions = {
        conversation: conversation.scrollTop,
        sessions: sessions.scrollTop,
        main: main instanceof HTMLElement ? main.scrollTop : 0,
        pageY: window.scrollY,
      };
    }

    return {
      conversationCanScroll: conversation.scrollHeight > conversation.clientHeight + 8,
      sessionsVisible: sessions !== null,
      sessionsCanScroll:
        sessions !== null && sessions.scrollHeight > sessions.clientHeight + 8,
      afterConversation,
      afterSessions,
    };
  });
}

test("authenticated Ask splits Sessions and conversation scroll when signed in", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Ask", level: 1 })).toBeVisible();
    await expect(page.getByRole("region", { name: "Conversation" })).toBeVisible();
    const probe = await measureAskScrollIndependence(page);
    expect(probe.conversationCanScroll).toBe(true);
    expect(probe.afterConversation.conversation).toBeGreaterThan(0);
    expect(probe.afterConversation.sessions).toBe(0);
    expect(probe.afterConversation.main).toBe(0);
    expect(probe.afterConversation.pageY).toBe(0);
    const composer = page.getByLabel("Message");
    const box = await composer.boundingBox();
    expect(box).not.toBeNull();
    expect(box?.y ?? -1).toBeGreaterThanOrEqual(0);
    expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(viewport.height);
    if (viewport.width >= 1280) {
      expect(probe.sessionsVisible).toBe(true);
      expect(probe.sessionsCanScroll).toBe(true);
      expect(probe.afterSessions?.sessions ?? 0).toBeGreaterThan(0);
      expect(probe.afterSessions?.conversation).toBe(
        probe.afterConversation.conversation,
      );
      expect(probe.afterSessions?.main).toBe(0);
      expect(probe.afterSessions?.pageY).toBe(0);
      const newSession = page.getByRole("button", { name: "New" });
      const newBox = await newSession.boundingBox();
      expect(newBox).not.toBeNull();
      expect(newBox?.y ?? -1).toBeGreaterThanOrEqual(0);
    } else {
      expect(probe.sessionsVisible).toBe(false);
    }
  }
});
