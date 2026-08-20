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
  await expect(page.getByRole("link", { name: "Team" })).toHaveAttribute(
    "href",
    "/team",
  );
  await expect(page.getByRole("link", { name: "Tools" })).toHaveAttribute(
    "href",
    "/tools",
  );
  await expect(page.getByRole("link", { name: "Curation" })).toHaveAttribute(
    "href",
    "/curation",
  );
  await expect(page.getByRole("link", { name: "Usage" })).toHaveAttribute(
    "href",
    "/usage",
  );
  await expect(page.getByRole("link", { name: "Profile" })).toHaveAttribute(
    "href",
    "/profile",
  );
});

test("unauthenticated administration routes redirect to login", async ({
  page,
}) => {
  for (const path of ["/team", "/tools", "/usage", "/profile", "/curation"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/login/);
  }
});

test("stubbed company usage 403 stays forbidden copy when signed in", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.route("http://127.0.0.1:8000/usage/company", async (route) => {
    await route.fulfill({
      status: 403,
      contentType: "application/json",
      body: JSON.stringify({ detail: "forbidden" }),
    });
  });
  await page.goto("/usage");
  await expect(page.getByTestId("budget-editor-unavailable")).toBeVisible();
  await expect(page.locator("input[type='range']")).toHaveCount(0);
  await expect(page.getByTestId("audit-unavailable")).toBeVisible();
});
