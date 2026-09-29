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

test("authenticated desktop navigation is a Field top bar when a session exists", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto("/");
  const nav = page.getByTestId("app-shell-nav");
  await expect(nav).toBeVisible();
  const box = await nav.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.height).toBeGreaterThanOrEqual(40);
  expect(box!.height).toBeLessThan(120);
  expect(box!.width).toBeGreaterThan(400);
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
  await expect(page.getByText("Smart RAG").filter({ visible: true })).toBeVisible();
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
