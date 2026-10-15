/**
 * Historical Ask citation journey: Acrobat label 12, not file page 25.
 */

import { expect, test, type Page } from "@playwright/test";
import {
  AI_AGENTS_CHIP_LABEL,
  AI_AGENTS_DRAWER_TITLE,
  AI_AGENTS_FORBIDDEN_FILE_PAGE,
  AI_AGENTS_UNIQUE_SPAN,
} from "../../src/lib/pdf-paragraph-citation-fixture";
import { signInLiveMember } from "./live-auth";

const CONVERSATION_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";

/**
 * Stub conversation history with a mapped PDF citation labeled page 12.
 *
 * @param page - Playwright page after live sign-in.
 */
async function stubCitedConversation(page: Page): Promise<void> {
  await page.route("**/conversations", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          conversation_id: CONVERSATION_ID,
          creator_user_id: "user-1",
          title: "AI Agents refunds",
          created_at: "2026-09-15T00:00:00Z",
        },
      ]),
    });
  });
  await page.route(`**/conversations/${CONVERSATION_ID}/messages**`, async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        items: [
          {
            message_id: "m-user",
            role: "user",
            content: "What is the refund period?",
            created_at: "2026-09-15T00:00:00Z",
            run_id: null,
            citations: [],
          },
          {
            message_id: "m-assistant",
            role: "assistant",
            content: AI_AGENTS_UNIQUE_SPAN,
            created_at: "2026-09-15T00:00:10Z",
            run_id: "run-1",
            citations: [
              {
                citation_id: "cite-1",
                citation_index: 0,
                chunk_id: "chunk-1",
                source_kind: "company_document",
                paragraph_index: 0,
                document_title: "AI Agents",
                pdf_page_number: 25,
                evidence_excerpt: AI_AGENTS_UNIQUE_SPAN,
                provenance: { page_label: "12", page_number: 12 },
                source_unavailable: false,
              },
            ],
          },
        ],
        next_before_id: null,
      }),
    });
  });
}

test("historical company PDF chip uses Acrobat label 12 not file page 25", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await stubCitedConversation(page);
  await page.goto("/");
  const expandSessions = page.getByRole("button", { name: "Expand sessions" });
  if (await expandSessions.isVisible()) {
    await expandSessions.click();
  }
  await page.getByRole("button", { name: "AI Agents refunds" }).click();
  const chip = page.getByRole("button", { name: `Citation 0, ${AI_AGENTS_CHIP_LABEL}` });
  await expect(chip).toBeVisible();
  await expect(page.getByText(AI_AGENTS_FORBIDDEN_FILE_PAGE)).toHaveCount(0);
  await chip.click();
  const drawer = page.getByRole("dialog");
  await expect(drawer.getByRole("heading", { name: AI_AGENTS_DRAWER_TITLE })).toBeVisible();
  await expect(drawer.getByText("Supporting passage")).toBeVisible();
  await expect(drawer.getByText(AI_AGENTS_UNIQUE_SPAN)).toBeVisible();
  await expect(drawer.getByText(AI_AGENTS_FORBIDDEN_FILE_PAGE)).toHaveCount(0);
});
