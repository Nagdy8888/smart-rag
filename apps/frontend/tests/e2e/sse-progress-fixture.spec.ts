/**
 * Deterministic Ask progress/reveal journey using checked-in SSE fixtures.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

// Playwright 1.62 treats `import.meta.url` as native ESM and then emits
// `require()`, which throws. Load fixtures from the frontend package cwd.
const FIXTURE_DIR = join(process.cwd(), "tests", "fixtures", "sse");
const COMPANY_SSE = readFileSync(join(FIXTURE_DIR, "company-progress.sse"), "utf8");
const CONVERSATION_ID = "11111111-1111-4111-8111-111111111111";
const RUN_ID = "22222222-2222-4222-8222-222222222222";

/**
 * Fulfill FastAPI Ask endpoints with the company progress fixture.
 *
 * @param page - Playwright page after live sign-in.
 */
async function interceptCompanyProgress(
  page: import("@playwright/test").Page,
): Promise<void> {
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
  await page.route("**/health/ready", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        query_ready: true,
        detail: "ready",
        rate_limit_degraded: false,
        dependencies: [],
      }),
    });
  });
  await page.route("**/conversations", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          conversation_id: CONVERSATION_ID,
          creator_user_id: "user-1",
          title: "Fixture question",
          created_at: "2026-08-26T00:00:00Z",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          conversation_id: CONVERSATION_ID,
          creator_user_id: "user-1",
          title: "Fixture question",
          created_at: "2026-08-26T00:00:00Z",
        },
      ]),
    });
  });
  await page.route(`**/conversations/${CONVERSATION_ID}/messages**`, async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          run_id: RUN_ID,
          stream_path: `/runs/${RUN_ID}/events`,
          reconnect: false,
          reservation_id: "res-1",
          route_family: "company",
          status: "running",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], next_before_id: null }),
    });
  });
  await page.route(`**/runs/${RUN_ID}/events**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: COMPANY_SSE,
    });
  });
}

test("company fixture shows waiting then verify then skippable verified answer", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await interceptCompanyProgress(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Send" })).toBeEnabled();
  await page.getByRole("textbox").fill("SYNTHETIC fixture question");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByTestId("run-progress-timeline")).toBeVisible();
  await expect(page.getByText("PUBLIC_FINAL")).toHaveCount(0);
  await expect(page.getByText(/Verifying|Verified/)).toBeVisible();
  await expect(page.getByTestId("verified-answer-reveal")).toBeVisible();
  const skip = page.getByRole("button", { name: "Show full answer" });
  if (await skip.isVisible()) {
    await skip.click();
  }
  await expect(page.getByText("PUBLIC_FINAL")).toBeVisible();
  await expect(page.getByText("SECRET_QUERY")).toHaveCount(0);
  await expect(page.getByText("SECRET_DRAFT")).toHaveCount(0);
});

test("reduced motion renders the full verified fixture immediately", async ({
  page,
  request,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await signInLiveMember(page, request);
  await interceptCompanyProgress(page);
  await page.goto("/");
  await page.getByRole("textbox").fill("SYNTHETIC fixture question");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("PUBLIC_FINAL")).toBeVisible();
  await expect(page.getByRole("button", { name: "Show full answer" })).toHaveCount(0);
});
