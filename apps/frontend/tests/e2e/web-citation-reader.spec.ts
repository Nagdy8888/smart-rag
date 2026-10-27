/** Web citations use the same supporting-passage reader as company sources. */
import { expect, test } from "@playwright/test";
import { signInLiveMember } from "./live-auth";

const conversation = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const citation = {
  citation_id: "web-cite-1", citation_index: 1, chunk_id: null,
  source_kind: "web", paragraph_index: 0, source_unavailable: false,
  web_source_id: "web-source-1", source_url: "https://www.rfc-editor.org/rfc/rfc6585",
  evidence_excerpt: "HTTP 429 indicates too many requests.",
  provenance: { title: "RFC 6585 — Too-Many-Requests" },
};
test("web source chip opens saved evidence on desktop and mobile", async ({ page, request }) => {
  await signInLiveMember(page, request);
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/conversations", route => route.fulfill({ json: [{
    conversation_id: conversation, creator_user_id: "user-1", title: "Web citation UI fixture",
    created_at: "2026-10-26T00:00:00Z",
  }] }));
  await page.route(`**/conversations/${conversation}`, route => route.fulfill({ json: {
    conversation_id: conversation, creator_user_id: "user-1", title: "Web citation UI fixture",
    created_at: "2026-10-26T00:00:00Z",
  } }));
  await page.route(`**/conversations/${conversation}/knowledge-scope`, route => route.fulfill({ json: {
    document_id: null, title: null, unavailable: false, enabled: false,
  } }));
  await page.route(`**/conversations/${conversation}/messages**`, route => route.fulfill({ json: {
    items: [{ message_id: "question-1", role: "user", content: "What does HTTP 429 mean?", created_at: "2026-10-26T00:00:00Z", run_id: "web-run-1" }, { message_id: "message-1", role: "assistant", content: "HTTP 429 indicates too many requests.",
      created_at: "2026-10-26T00:00:01Z", run_id: "web-run-1", citation_count: 1,
      source_kind: "web", citations: [citation] }], next_before_id: null,
  } }));
  await page.route("**/runs/web-run-1/citations**", route => route.fulfill({ json:
    new URL(route.request().url()).pathname.endsWith("/web-cite-1") ? citation : [citation],
  }));
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    await page.goto("/");
    if (viewport.width < 768) await page.getByRole("button", { name: "Sessions", exact: true }).click();
    await page.getByRole("button", { name: "Web citation UI fixture", exact: true }).click();
    const sources = page.getByRole("region", { name: "Conversation", exact: true }).getByRole("button", { name: "Sources (1)", exact: true });
    await sources.click();
    const chip = page.getByRole("button", { name: /Citation 1.*RFC/ });
    await chip.focus();
    await page.keyboard.press("Enter");
    const reader = page.getByRole("dialog").last();
    await expect(reader.getByText("Supporting passage", { exact: true })).toBeVisible();
    await expect(reader).toContainText("HTTP 429 indicates too many requests.");
    await expect(reader.getByRole("link", { name: /Open web page/ })).toHaveAttribute("href", citation.source_url);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
    await page.screenshot({ animations: "disabled", path: `../../.private-eval/user-app-review-20261026/web-reader-${viewport.width}.png` });
    await page.keyboard.press("Escape");
    await expect(sources).toBeFocused();
  }
  expect(errors).toEqual([]);
});

test("read-only user walkthrough opens existing questions, company evidence and overview", async ({ page, request }) => {
  await signInLiveMember(page, request);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "Live diagnostic: 50 questions (Oct 26)", exact: true }).click();
  const transcript = page.getByRole("region", { name: "Conversation", exact: true });
  await expect(transcript).toContainText("Why is that a problem when an agent needs frequent queries?");
  await transcript.getByRole("button", { name: "Sources (2)", exact: true }).first().click();
  await page.getByRole("button", { name: /^Citation / }).first().click();
  const reader = page.getByRole("dialog").last();
  await expect(reader).toContainText("Supporting passage");
  await expect(reader.getByText("Loading passage…", { exact: true })).toHaveCount(0);
  await page.screenshot({ animations: "disabled", path: "../../.private-eval/user-app-review-20261026/company-reader-live.png" });
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Admin", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Workspace overview", exact: true })).toBeVisible();
  await page.screenshot({ animations: "disabled", path: "../../.private-eval/user-app-review-20261026/overview-live.png" });
  await page.getByRole("link", { name: "Documents", exact: true }).click();
  await expect(page.getByRole("main")).toContainText("building-applications-with-ai-agents");
  await page.screenshot({ animations: "disabled", path: "../../.private-eval/user-app-review-20261026/documents-live.png" });
});
