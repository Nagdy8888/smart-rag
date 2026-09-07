/**
 * Hosted Auth helpers for Playwright live specs.
 * Skip when FastAPI is down or a provisioned live user is not configured.
 */

import {
  expect,
  test,
  type APIRequestContext,
  type Page,
} from "@playwright/test";

const LOCAL_FASTAPI = "http://127.0.0.1:8000";

/**
 * Fetch live FastAPI readiness, or null when the API is down.
 *
 * @param request - Playwright API request fixture.
 * @returns JSON body, or null.
 */
export async function fetchLocalReady(
  request: APIRequestContext,
): Promise<Record<string, unknown> | null> {
  try {
    const response = await request.get(`${LOCAL_FASTAPI}/health/ready`, {
      timeout: 3000,
    });
    if (!response.ok()) {
      return null;
    }
    return (await response.json()) as Record<string, unknown>;
  } catch {
    return null;
  }
}

/**
 * Sign in a provisioned hosted member through the login form.
 *
 * Requires `E2E_LIVE_EMAIL` and `E2E_LIVE_PASSWORD` (never logged). Skips
 * when either is unset, or when FastAPI at `127.0.0.1:8000` is unreachable.
 * Does not create users and does not call Auth Admin APIs.
 *
 * @param page - Playwright page.
 * @param request - Playwright API request fixture.
 * @returns Nothing. Skips when credentials or FastAPI are unavailable.
 */
export async function signInLiveMember(
  page: Page,
  request: APIRequestContext,
): Promise<void> {
  const email = (process.env.E2E_LIVE_EMAIL ?? "").trim();
  const password = (process.env.E2E_LIVE_PASSWORD ?? "").trim();
  if (!email || !password) {
    test.skip(true, "E2E_LIVE_EMAIL/E2E_LIVE_PASSWORD not set");
    return;
  }
  const ready = await fetchLocalReady(request);
  if (ready === null) {
    test.skip(true, "local FastAPI is unreachable at 127.0.0.1:8000");
    return;
  }
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByRole("textbox", { name: "Password" }).fill(password);
  const tokenOk = page.waitForResponse(
    (response) => response.url().includes("/auth/v1/token") && response.ok(),
    { timeout: 20_000 },
  );
  await page.getByRole("button", { name: "Sign in" }).click();
  await tokenOk;
  await page.goto("/");
  await expect(page).not.toHaveURL(/\/login/);
}
