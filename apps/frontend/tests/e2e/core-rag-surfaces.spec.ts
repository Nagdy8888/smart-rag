import { expect, test } from "@playwright/test";
import { DOCUMENT_NOT_FOUND_COPY } from "../../src/lib/citation-drawer";
import { signInLiveMember } from "./live-auth";

test("login has no console nav; authenticated chrome includes Ask Documents Tables Graph", async ({
  page,
  request,
}) => {
  await page.goto("/login");
  await expect(page.getByTestId("app-shell-nav")).toHaveCount(0);
  await signInLiveMember(page, request);
  await page.goto("/");
  await expect(page.getByRole("link", { name: "Ask" })).toHaveAttribute("href", "/");
  await expect(page.getByRole("link", { name: "Documents" })).toHaveAttribute(
    "href",
    "/documents",
  );
  await expect(page.getByRole("link", { name: "Graph" })).toHaveAttribute(
    "href",
    "/graph",
  );
  await expect(page.getByRole("link", { name: "Tables" })).toHaveAttribute(
    "href",
    "/tables",
  );
  await expect(page.getByRole("link", { name: "Team" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Profile" })).toHaveCount(0);
});

test("unauthenticated documents graph tables redirect to login", async ({ page }) => {
  await page.goto("/documents");
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/graph");
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/tables");
  await expect(page).toHaveURL(/\/login/);
});

test("unauthenticated document detail does not leak a title", async ({ page }) => {
  await page.goto("/documents/33333333-3333-4333-8333-333333333333");
  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByText("SECRET TITLE")).toHaveCount(0);
});

test("retired review-fixtures route returns production 404", async ({ page }) => {
  const retired = await page.goto("/review-fixtures");
  expect(retired?.status()).toBe(404);
  await expect(page).not.toHaveURL(/\/login/);
});

test("authenticated Auto chrome when a session exists", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Auto chat" })).toBeVisible();
  await expect(page.getByTestId("auto-label")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send" })).toBeVisible();
});

test("stubbed document 404 shows Not found without a title", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.route("http://127.0.0.1:8000/documents/**", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ title: "SECRET TITLE", detail: "not_found" }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/documents/33333333-3333-4333-8333-333333333333");
  await expect(page.getByText(DOCUMENT_NOT_FOUND_COPY)).toBeVisible();
  await expect(page.getByText("SECRET TITLE")).toHaveCount(0);
});
