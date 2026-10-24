import { expect, test } from "@playwright/test";
import { handshakeBelowMinCopy } from "../../src/lib/handshake";

const PUBLIC_AUTH_PATHS = [
  "/login",
  "/signup",
  "/forgot-password",
] as const;

const RETIRED_PATHS = [
  "/unavailable/GAP-07-07",
  "/unavailable/GAP-07-08",
  "/review-fixtures",
] as const;

const PROTECTED_PATHS = [
  "/",
  "/documents",
  "/documents/33333333-3333-4333-8333-333333333333",
  "/graph",
  "/tables",
  "/team",
  "/tools",
  "/curation",
  "/usage",
  "/profile",
  "/admin",
  "/account",
  "/invitations/accept",
] as const;

test("unauthenticated shipped routes redirect to login except public auth pages", async ({
  page,
}) => {
  for (const path of PROTECTED_PATHS) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
  for (const path of PUBLIC_AUTH_PATHS) {
    await page.goto(path);
    await expect(page).toHaveURL(new RegExp(`${path.replaceAll("/", "\\/")}`));
  }
});

test("retired review and gap routes 404 instead of login or Unavailable chrome", async ({
  page,
}) => {
  for (const path of RETIRED_PATHS) {
    const response = await page.goto(path);
    expect(response?.status()).toBe(404);
    await expect(page).not.toHaveURL(/\/login/);
  }
});

test("login chrome has skip link and Sign in without console nav or Stitch frames", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
  await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
  await expect(page.getByText("Stitch")).toHaveCount(0);
  await expect(page.getByText("frame_04")).toHaveCount(0);
});

test("retired gap routes do not serve recovery or bootstrap chrome", async ({
  page,
}) => {
  const first = await page.goto("/unavailable/GAP-07-07");
  expect(first?.status()).toBe(404);
  await expect(page.getByLabel(/recovery/i)).toHaveCount(0);
  const second = await page.goto("/unavailable/GAP-07-08");
  expect(second?.status()).toBe(404);
  await expect(page.getByLabel(/company/i)).toHaveCount(0);
});

test("query handshake mismatch does not prevent signing in", async ({ page }) => {
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
  await expect(page.getByText(handshakeBelowMinCopy())).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Sign in", exact: true })).toBeEnabled();
});

test("unauthenticated document 404 still redirects to login", async ({ page }) => {
  await page.route("http://127.0.0.1:8000/documents/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ title: "SECRET TITLE", detail: "not_found" }),
    });
  });
  await page.goto("/documents/33333333-3333-4333-8333-333333333333");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("SECRET TITLE")).toHaveCount(0);
});

test("login response includes CSP without Tailwind CDN and with API origin", async ({
  page,
}) => {
  const response = await page.goto("/login");
  expect(response).not.toBeNull();
  const csp = response?.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("default-src 'self'");
  expect(csp).toContain("object-src 'none'");
  expect(csp).not.toContain("cdn.tailwindcss.com");
  expect(csp).not.toContain("fonts.googleapis.com");
  expect(csp).not.toContain("https://*.supabase.co");
  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
  expect(csp).toContain(new URL(apiBase).origin);
});
