import { expect, test } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

test("authenticated chrome includes administration nav links", async ({
  page,
  request,
}) => {
  await page.goto("/login");
  await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
  await signInLiveMember(page, request);
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Ask" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Team" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Tools" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Curation" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Usage" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Profile" })).toHaveCount(0);
});

test("unauthenticated administration routes redirect to login", async ({
  page,
}) => {
  for (const path of ["/team", "/tools", "/usage", "/profile", "/curation", "/admin"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
});

test("stubbed company usage 403 stays forbidden copy when signed in", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.route("**/admin/graph/entity-rules**", async (route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "forbidden" }),
    });
  });
  await page.route("**/usage/company", async (route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "forbidden" }),
    });
  });
  await page.goto("/usage");
  await expect(page.getByText("You don’t have access.")).toBeVisible();
  await expect(page.locator("input[type='range']")).toHaveCount(0);
  await expect(page.getByTestId("audit-unavailable")).toHaveCount(0);
});
