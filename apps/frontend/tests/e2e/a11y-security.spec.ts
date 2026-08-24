import { expect, test } from "@playwright/test";
import { GENERIC_PRODUCTION_ERROR } from "../../src/lib/failure-copy";
import { signInLiveMember } from "./live-auth";

test("Tab order on login starts at the skip link and focuses main", async ({
  page,
}) => {
  await page.goto("/login");
  await page.keyboard.press("Tab");
  const skip = page.getByRole("link", { name: "Skip to main content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main")).toBeFocused();
});

test("200% zoom keeps sign-in controls visible", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 400 });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("mobile Menu disclosure is keyboard accessible at 390px when signed in", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  const menu = page.getByText("Menu", { exact: true });
  await expect(menu).toBeVisible();
  await menu.press("Enter");
  await expect(page.getByRole("link", { name: "Ask" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Profile" })).toHaveCount(0);
});

test("login never shows Auth exception text", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText(GENERIC_PRODUCTION_ERROR)).toHaveCount(0);
  await expect(page.getByText(/Traceback|AuthApiError|GoTrue/i)).toHaveCount(0);
});
