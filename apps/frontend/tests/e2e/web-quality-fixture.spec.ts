/** Entirely mocked Auth/API journey. No admission, providers or billed requests. */
import { expect, test } from "@playwright/test";

const conversation = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const run = "22222222-2222-4222-8222-222222222222";
const created = "2026-10-28T00:00:00Z";
const citation = (index: number) => ({ citation_id: `cite-${index}`, citation_index: index,
  chunk_id: null, source_kind: "web", source_unavailable: false, web_source_id: "source-1",
  source_url: "https://www.rfc-editor.org/rfc/rfc6585", evidence_excerpt: index === 0 ? "429 means too many requests." : "Retry-After is optional.",
  provenance: { title: "RFC 6585", url: "https://www.rfc-editor.org/rfc/rfc6585" } });

for (const width of [1440, 390]) test(`Web answer, citations and reload at ${width}px`, async ({ page, context }) => {
  await page.setViewportSize({ width, height: 1000 });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  const user = { id: "11111111-1111-4111-8111-111111111111", email: "fixture@example.test", aud: "authenticated", role: "authenticated" };
  const jwt = `${Buffer.from(JSON.stringify({ alg: "HS256", typ: "JWT" })).toString("base64url")}.${Buffer.from(JSON.stringify({ sub: user.id, exp: 4102444800, role: "authenticated" })).toString("base64url")}.fixture`;
  const session = { access_token: jwt, refresh_token: "fixture", expires_at: 4102444800, expires_in: 3600, token_type: "bearer", user };
  const publicUrl = process.env.WEB_FIXTURE_SUPABASE_URL ?? "http://127.0.0.1:3041";
  const cookieName = `sb-${new URL(publicUrl).hostname.split(".")[0]}-auth-token`;
  await context.addCookies([{ name: cookieName, value: `base64-${Buffer.from(JSON.stringify(session)).toString("base64url")}`, domain: "127.0.0.1", path: "/" }]);
  await page.route(`${publicUrl}/**`, route => route.fulfill({ json: user }));
  let answered = false;
  let submissions = 0;
  const answer = "رمز 429 يعني إرسال طلبات كثيرة. [[cite:0]]\n\nالترويسة اختيارية. [[cite:1]]";
  await page.route("http://127.0.0.1:8000/**", async route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = {};
    if (path === "/api/meta") body = { api_version: "1", sse_schema_version: "1", min_client_version: "0.1.0", web_search_enabled: true };
    else if (path === "/me") body = { user_id: user.id, role: "member", authorization_version: 1, email: user.email };
    else if (path === "/health/ready") body = { status: "ok", query_ready: true, detail: "ready", dependencies: [], rate_limit_degraded: false };
    else if (path === "/conversations") body = [{ conversation_id: conversation, creator_user_id: user.id, title: "Web fixture", created_at: created }];
    else if (path === `/conversations/${conversation}`) body = { conversation_id: conversation, creator_user_id: user.id, title: "Web fixture", created_at: created };
    else if (path.endsWith("/knowledge-scope")) body = { document_id: null, enabled: false, unavailable: false };
    else if (path.endsWith("/messages")) {
      if (route.request().method() === "POST") {
        submissions++; answered = true;
        body = { run_id: run, stream_path: `/runs/${run}/events`, reservation_id: "res-fixture", route_family: "web_research", status: "running" };
        await route.fulfill({ status: 202, json: body }); return;
      }
      body = { items: answered ? [
        { message_id: "failed-question", role: "user", content: "Previous failed question", run_id: "failed-run", run_status: "failed", created_at: created, requested_search_scope: "web" },
        { message_id: "question", role: "user", content: "اشرح رمز 429 بالعربية", run_id: run, created_at: created, requested_search_scope: "web" },
        { message_id: "answer", role: "assistant", content: answer, run_id: run, created_at: created, requested_search_scope: "web", answer_origin: "web", citation_count: 2, source_kind: "web" },
      ] : [], next_before_id: null };
    } else if (path.endsWith("/events")) {
      const frames = [ ["status", { stage: "web_search", status: "running" }], ["status", { stage: "web_read", status: "running" }],
        ["status", { stage: "verify_answer", status: "running" }], ["answer_origin", { origin: "web" }],
        ["token_delta", { text: answer }], ["completed", { status: "completed" }] ];
      await route.fulfill({ contentType: "text/event-stream", body: frames.map(([event, data], index) => `event: ${event}\nid: ${index+1}\ndata: ${JSON.stringify(data)}\n\n`).join("") }); return;
    } else if (path.endsWith("/citations")) body = [citation(0), citation(1)];
    else if (/\/citations\/cite-[01]$/.test(path)) body = citation(Number(path.slice(-1)));
    await route.fulfill({ json: body });
  });
  await page.goto("/");
  if (width === 390) await page.getByRole("button", { name: "Sessions", exact: true }).click();
  await page.getByRole("button", { name: "Web fixture", exact: true }).click();
  await page.getByRole("radio", { name: "Web", exact: true }).click();
  await page.getByRole("textbox").fill("اشرح رمز 429 بالعربية");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await expect(page.getByText("الترويسة اختيارية.", { exact: false }).first()).toBeVisible();
  for (const reload of [false, true]) {
    if (reload) {
      await page.reload();
      if (width === 390) await page.getByRole("button", { name: "Sessions", exact: true }).click();
      await page.getByRole("button", { name: "Web fixture", exact: true }).click();
    }
    await expect(page.getByRole("radio", { name: "Web", exact: true })).toHaveAttribute("aria-checked", "true");
    await expect(page.getByText("This question could not be completed. No answer was saved.")).toBeVisible();
    const transcript = page.getByRole("region", { name: "Conversation", exact: true });
    for (const index of [1, 2]) {
      await transcript.getByRole("button", { name: `Citation ${index}, RFC 6585`, exact: true }).first().click();
      await expect(page.getByRole("dialog").last()).toContainText(index === 1 ? "429 means too many requests." : "Retry-After is optional.");
      await expect(page.getByRole("link", { name: /Open web page/ })).toHaveAttribute("href", citation(0).source_url);
      await page.keyboard.press("Escape");
    }
    await transcript.getByRole("button", { name: "Sources (1 page)", exact: true }).click();
    await expect(page.getByRole("dialog", { name: "Sources (1 page)", exact: true })).toBeVisible();
    await page.keyboard.press("Escape");
  }
  // A long company-document source list appears only inside the Sources sheet.
  const companyCitations = Array.from({ length: 10 }, (_, index) => ({
    citation_id: `company-${index}`, citation_index: index, chunk_id: `chunk-${index}`,
    source_kind: "company_document", source_unavailable: false, paragraph_index: 0,
    document_title: "building-applications-with-ai-agents-designing-and-implementing-multiagent-systems-1 (1).pdf",
    pdf_page_number: 290 - index, provenance: {},
  }));
  await page.route(`**/conversations/${conversation}/messages**`, route => route.fulfill({ json: {
    items: [{ message_id: "company-answer", role: "assistant", content: "A concise company answer.",
      created_at: created, run_id: run, requested_search_scope: "company_documents",
      answer_origin: "company_documents", citation_count: 10, source_kind: "company_document" }], next_before_id: null,
  } }));
  await page.route(`**/runs/${run}/citations`, route => route.fulfill({ json: companyCitations }));
  await page.reload();
  if (width === 390) await page.getByRole("button", { name: "Sessions", exact: true }).click();
  await page.getByRole("button", { name: "Web fixture", exact: true }).click();
  const companyTranscript = page.getByRole("region", { name: "Conversation", exact: true });
  await expect(companyTranscript).toContainText("A concise company answer.");
  await expect(companyTranscript.getByRole("button", { name: /^Citation / })).toHaveCount(0);
  await expect(companyTranscript.getByText(/building-applications-with-ai-agents/)).toHaveCount(0);
  await page.screenshot({ animations: "disabled", path: `../../.private-eval/sources-on-demand-chat-${width}.png`, fullPage: true });
  await companyTranscript.getByRole("button", { name: /^Sources \(10 / }).click();
  const sources = page.getByRole("dialog").last();
  await expect(sources.getByRole("button", { name: /^Citation / })).toHaveCount(10);
  await expect(sources.getByRole("button", { name: /^Citation / }).first()).toBeVisible();
  await page.screenshot({ animations: "disabled", path: `../../.private-eval/sources-on-demand-sheet-${width}.png`, fullPage: true });
  await page.keyboard.press("Escape");
  expect(submissions).toBe(1);
  expect(errors).toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)).toBe(false);
  await page.screenshot({ animations: "disabled", path: `../../.private-eval/web-quality-${width}.png`, fullPage: true });
});
