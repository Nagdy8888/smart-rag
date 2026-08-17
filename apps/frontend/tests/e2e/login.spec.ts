import { expect, test } from "@playwright/test";
import { limitationCopy } from "../../src/lib/limitations";
import { handshakeBelowMinCopy } from "../../src/lib/handshake";
import { CALLBACK_FAILED, MFA_REQUIRED_BANNER } from "../../src/lib/auth/copy";
import { fetchLocalReady } from "./live-auth";

test("unauthenticated console shows sign-in", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Sign up" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Forgot password" })).toBeVisible();
  await expect(page.getByText("Stitch")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "API readiness" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Signed outage copy" }),
  ).toBeVisible();
  await expect(page.getByText(limitationCopy("bm25_unavailable"))).toBeVisible();
  await expect(page.getByText(limitationCopy("graph_outage"))).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Continue with Google (when enabled)" }),
  ).toBeDisabled();
});

test("browser readiness panel matches live GET /health/ready", async ({
  page,
  request,
}) => {
  const ready = await fetchLocalReady(request);
  if (ready === null) {
    test.skip(true, "local FastAPI is unreachable at 127.0.0.1:8000");
    return;
  }
  await page.goto("/login");
  const panel = page.getByTestId("api-readiness");
  await expect(panel).toBeVisible();
  await expect(page.getByTestId("query-ready")).toHaveText(
    String(ready.query_ready),
  );
  const dependencies = Array.isArray(ready.dependencies)
    ? ready.dependencies
    : [];
  for (const item of dependencies) {
    if (
      item === null ||
      typeof item !== "object" ||
      !("name" in item) ||
      !("status" in item)
    ) {
      continue;
    }
    const name = String(item.name);
    const status = String(item.status);
    await expect(page.getByTestId(`dep-${name}`)).toHaveText(status);
  }
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

test("MFA required banner copy is on the challenge surface", async ({ page }) => {
  await page.goto("/mfa/challenge");
  await expect(page.getByText(MFA_REQUIRED_BANNER)).toBeVisible();
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

test("GAP-07-07 unavailable page has no recovery-code control", async ({
  page,
}) => {
  await page.goto("/unavailable/GAP-07-07");
  await expect(page.getByRole("heading", { name: "Unavailable" })).toBeVisible();
  await expect(page.getByText("GAP-07-07", { exact: true })).toBeVisible();
  await expect(page.getByLabel(/recovery/i)).toHaveCount(0);
  await expect(page.locator("input")).toHaveCount(0);
});
