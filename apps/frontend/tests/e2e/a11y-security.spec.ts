import { expect, test } from "@playwright/test";
import { GENERIC_PRODUCTION_ERROR } from "../../src/lib/failure-copy";

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

test("200% zoom keeps composer, banners, and chips visible", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 400 });
  await page.goto("/login");
  const fixtures = page.getByTestId("reviewed-content-fixtures");
  await expect(fixtures).toBeVisible();
  await expect(page.getByLabel("Stub composer")).toBeVisible();
  await expect(page.getByRole("button", { name: "Citation 1" })).toBeVisible();
  await expect(page.getByRole("status").first()).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Sign in" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});

test("mobile Menu disclosure is keyboard accessible at 390px", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  const menu = page.getByText("Menu", { exact: true });
  await expect(menu).toBeVisible();
  await menu.press("Enter");
  await expect(page.getByRole("link", { name: "Chat" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Profile" })).toBeVisible();
});

test("login never shows Auth exception text", async ({ page }) => {
  await page.goto("/login");
  await expect(page.getByText(GENERIC_PRODUCTION_ERROR)).toHaveCount(0);
  await expect(page.getByText(/Traceback|AuthApiError|GoTrue/i)).toHaveCount(0);
});
