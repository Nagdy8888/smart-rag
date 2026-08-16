import { expect, test } from "@playwright/test";

test("developer console shows sign-in, not production Stitch chrome", async ({
  page,
}) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", { name: "Smart RAG developer console" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByText("Stitch")).toHaveCount(0);
});
