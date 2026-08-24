import { expect, test } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

test("login has no console navigation", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/login");
  await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toHaveAttribute("href", "#main");
  await expect(page.locator("#main")).toBeVisible();
});

test("authenticated desktop navigation is 232px when a session exists", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  const nav = page.getByTestId("app-shell-nav");
  await expect(nav).toBeVisible();
  const width = await nav.evaluate((element) => element.getBoundingClientRect().width);
  expect(width).toBe(232);
  await expect(page.getByRole("link", { name: "Ask" })).toHaveAttribute(
    "href",
    "/",
  );
});

test("authenticated mobile keeps compact brand and a menu control", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await expect(page.getByText("Smart RAG").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Open navigation" })).toBeVisible();
  await expect(page.locator("#main")).toBeVisible();
});

test("reduced motion disables authored transitions", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  const duration = await page.evaluate(() => {
    const probe = document.createElement("div");
    probe.style.transitionDuration = "1s";
    document.body.append(probe);
    const value = getComputedStyle(probe).transitionDuration;
    probe.remove();
    return value;
  });
  expect(["0.01ms", "0s", "0.00001s", "1e-05s"]).toContain(duration);
});
