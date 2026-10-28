/** Read-only inspection of the finished diagnostic; never submits a question. */
import { expect, test } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

test("recorded Web failures remain visible after reload on desktop and mobile", async ({ page, request }) => {
  await signInLiveMember(page, request);
  const paidRequests: string[] = [];
  page.on("request", outgoing => {
    if (outgoing.method() === "POST" && /\/conversations\/[^/]+\/messages(?:\?|$)/.test(outgoing.url())) paidRequests.push(outgoing.url());
  });
  for (const width of [1440, 390]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/");
    if (width === 390) await page.getByRole("button", { name: "Sessions", exact: true }).click();
    await page.getByRole("button", { name: "Web diagnostic: checked answers (15)", exact: true }).click();
    const transcript = page.getByRole("region", { name: "Conversation", exact: true });
    await expect(transcript).toContainText("phantom-read behavior");
    await expect(transcript.getByText("This question could not be completed. No answer was saved.", { exact: true })).toHaveCount(3);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({ animations: "disabled", path: `../../.private-eval/finish-live-history-${width}.png` });
  }
  expect(paidRequests).toEqual([]);
});
