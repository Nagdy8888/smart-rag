import { expect, test } from "@playwright/test";
import { handshakeBelowMinCopy } from "../../src/lib/handshake";
import { CALLBACK_FAILED } from "../../src/lib/auth/copy";

test("unauthenticated console shows sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign up" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Forgot password" })).toBeVisible();
  await expect(page.getByText("Stitch")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "API readiness" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Signed outage copy" })).toHaveCount(0);
  await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /google/i })).toHaveCount(0);
});

test("login form is fully visible in the first mobile viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/login");
  const heading = page.getByRole("heading", { name: "Sign in" });
  const submit = page.getByRole("button", { name: "Sign in" });
  await expect(heading).toBeVisible();
  await expect(submit).toBeVisible();
  const box = await submit.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.y + box!.height).toBeLessThan(844);
  await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
});

test("signup and forgot-password links are visible from login", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByRole("link", { name: "Sign up" }).click();
  await expect(page.getByRole("heading", { name: "Sign up" })).toBeVisible();
  await page.goto("/login");
  await page.getByRole("link", { name: "Forgot password" }).click();
  await expect(page.getByRole("heading", { name: "Forgot password" })).toBeVisible();
});

test("callback replay shows generic failure copy", async ({ page }) => {
  await page.goto("/auth/callback");
  await expect(page).toHaveURL(/\/login\?error=callback/);
  await expect(page.getByText(CALLBACK_FAILED)).toBeVisible();
});

test("MFA challenge route is not a public Auth surface", async ({ page }) => {
  await page.goto("/mfa/challenge");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("button", { name: /google/i })).toHaveCount(0);
});

test("handshake banner appears when min_client_version is 9.0.0", async ({
  page,
}) => {
  await page.route("**/api/meta", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        api_version: "1",
        sse_schema_version: "1",
        min_client_version: "9.0.0",
      }),
    });
  });
  await page.goto("/login");
  await expect(page.getByText(handshakeBelowMinCopy())).toBeVisible();
});

test("retired GAP-07-07 route returns production 404", async ({
  page,
}) => {
  const response = await page.goto("/unavailable/GAP-07-07");
  expect(response?.status()).toBe(404);
  await expect(page).not.toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Unavailable" })).toHaveCount(0);
  await expect(page.getByLabel(/recovery/i)).toHaveCount(0);
});
