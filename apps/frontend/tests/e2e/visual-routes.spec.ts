/**
 * Desktop and mobile visual capture for Stitch-first routes.
 * Interaction assertions keep snapshots from hiding broken behavior.
 */
import { expect, test, type Page } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

const DESKTOP = { width: 1280, height: 800 } as const;
const MOBILE = { width: 390, height: 844 } as const;

/**
 * Capture a named screenshot after waiting for the main landmark.
 *
 * @param page - Playwright page.
 * @param name - Snapshot basename without extension.
 */
async function capture(page: Page, name: string): Promise<void> {
  await page.addStyleTag({
    content:
      "nextjs-portal,[data-next-badge],[data-next-badge-root],[data-next-mark]{display:none!important}",
  });
  await expect(page.locator("#main")).toBeVisible();
  await expect(page).toHaveScreenshot(`${name}.png`, {
    fullPage: true,
    animations: "disabled",
    maxDiffPixelRatio: 0.03,
  });
}

const PUBLIC_VISUAL: Array<{
  path: string;
  name: string;
  heading: string | RegExp;
}> = [
  { path: "/login", name: "login", heading: "Sign in" },
  { path: "/signup", name: "signup", heading: "Sign up" },
  { path: "/forgot-password", name: "forgot-password", heading: "Forgot password" },
];

test("public auth visual desktop and mobile", async ({ page }) => {
  await page.route("**/api/meta", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        api_version: "1",
        sse_schema_version: "1",
        min_client_version: "0.1.0",
      }),
    });
  });
  for (const route of PUBLIC_VISUAL) {
    await page.setViewportSize(DESKTOP);
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible();
    await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
    await capture(page, `${route.name}-desktop`);

    await page.setViewportSize(MOBILE);
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible();
    await capture(page, `${route.name}-mobile`);
  }
});

test("authenticated product routes visual when a session exists", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  const routes: Array<{ path: string; name: string; heading: string | RegExp }> = [
    { path: "/", name: "chat", heading: "Auto chat" },
    { path: "/documents", name: "documents", heading: /Document/ },
    { path: "/graph", name: "graph", heading: /Graph/ },
    { path: "/tables", name: "tables", heading: /table/i },
    { path: "/admin?tab=team", name: "admin-team", heading: "Team" },
    { path: "/admin?tab=tools", name: "admin-tools", heading: "Tools" },
    { path: "/admin?tab=curation", name: "admin-curation", heading: "Curation" },
    { path: "/admin?tab=usage", name: "admin-usage", heading: /Usage/ },
    { path: "/account", name: "account", heading: "Profile" },
  ];
  for (const route of routes) {
    await page.setViewportSize(DESKTOP);
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible();
    await capture(page, `${route.name}-desktop`);
    await page.setViewportSize(MOBILE);
    await page.goto(route.path);
    await expect(page.getByRole("heading", { name: route.heading }).first()).toBeVisible();
    await capture(page, `${route.name}-mobile`);
  }
});
