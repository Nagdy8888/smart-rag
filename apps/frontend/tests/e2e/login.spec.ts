import { expect, test, type APIRequestContext } from "@playwright/test";
import { limitationCopy } from "../../src/lib/limitations";

test("developer console shows sign-in, not production Stitch chrome", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Smart RAG developer console" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("signed_url is null")).toBeVisible();
  await expect(page.getByText("Stitch")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "API readiness" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Signed outage copy" }),
  ).toBeVisible();
  await expect(page.getByText(limitationCopy("bm25_unavailable"))).toBeVisible();
  await expect(page.getByText(limitationCopy("graph_outage"))).toBeVisible();
});

/**
 * Fetch live FastAPI readiness from the Playwright request context.
 *
 * @param request - Playwright API request fixture.
 * @returns JSON body, or null when FastAPI is down.
 */
async function fetchLocalReady(
  request: APIRequestContext,
): Promise<Record<string, unknown> | null> {
  try {
    const response = await request.get("http://127.0.0.1:8000/health/ready", {
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

test("browser readiness panel matches live GET /health/ready", async ({
  page,
  request,
}) => {
  const ready = await fetchLocalReady(request);
  if (ready === null) {
    test.skip(true, "local FastAPI is unreachable at 127.0.0.1:8000");
    return;
  }
  await page.goto("/");
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
