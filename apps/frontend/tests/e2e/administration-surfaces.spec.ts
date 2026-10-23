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
  await expect(page.getByTestId("admin-tab-evaluation")).toHaveCount(0);
});

test("member administration workspace has no Evaluation tab", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  await page.goto("/admin");
  await expect(page.getByTestId("admin-tab-evaluation")).toHaveCount(0);
});

test("stubbed owner Evaluation exam board starts development and shows the official report", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  let examPolls = 0;
  await page.route("**/api/meta", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        api_version: "1",
        sse_schema_version: "1",
        min_client_version: "0.1.0",
        pdf_eval_workspace: true,
      }),
    });
  });
  await page.route("**/me", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "owner-e2e",
        role: "owner",
        authorization_version: 1,
        upload_enabled: true,
      }),
    });
  });
  await page.route("**/admin/graph/entity-rules**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rules: [] }),
    });
  });
  await page.route("**/documents**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: "[]",
    });
  });
  await page.route("**/admin/pdf-eval/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (method === "GET" && url.includes("/admin/pdf-eval/status")) {
      await json({
        enabled: true,
        case_count: 1,
        revision: null,
        approved_count: 4,
        draft_count: 0,
        rejected_count: 0,
        stale_gold_count: 0,
        live_count: 1,
        remaining_capacity: 59,
        dataset_present: true,
        holdout_opened: false,
      });
      return;
    }
    if (method === "GET" && /\/admin\/pdf-eval\/cases(\?|$)/.test(url)) {
      await json({ revision: "", items: [], next_case_id: null });
      return;
    }
    if (method === "POST" && /\/admin\/pdf-eval\/exams$/.test(new URL(url).pathname)) {
      await json(
        {
          exam_run_id: "exam-e2e",
          status: "queued",
          dataset_hash: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
          replayed: false,
          holdout_opened: false,
        },
        202,
      );
      return;
    }
    if (method === "GET" && url.includes("/admin/pdf-eval/exams/exam-e2e")) {
      examPolls += 1;
      const status =
        examPolls === 1 ? "queued" : examPolls === 2 ? "running" : "succeeded";
      await json({
        exam_run_id: "exam-e2e",
        split: "development",
        status,
        dataset_hash: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        case_count: 2,
        completed_case_count: status === "succeeded" ? 2 : 1,
        holdout_opened: false,
        candidate_fingerprint:
          "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
      });
      return;
    }
    if (method === "GET" && url.includes("/admin/pdf-eval/reports/latest")) {
      const present = examPolls >= 3;
      await json(
        present
          ? {
              present: true,
              holdout_opened: false,
              exam_run_id: "exam-e2e",
              split: "development",
              dataset_hash:
                "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
              case_count: 2,
              hit_count: 2,
              hybrid_recall_at_10: 1,
              gates_pass: true,
              created_at: "2026-09-13T12:00:00+00:00",
            }
          : {
              present: false,
              holdout_opened: false,
              exam_run_id: null,
              split: "development",
              dataset_hash: null,
              case_count: null,
              hit_count: null,
              hybrid_recall_at_10: null,
              gates_pass: null,
              created_at: null,
            },
      );
      return;
    }
    if (method === "GET" && url.includes("/admin/pdf-eval/reports/exam-e2e/cases")) {
      await json({
        exam_run_id: "exam-e2e",
        missed_count: 0,
        items: [
          {
            case_id: "case-1",
            ordinal: 1,
            hit: true,
            gold_count: 1,
            ranked_hit_count: 1,
            latency_ms: 10,
          },
        ],
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/admin?tab=evaluation");
  await expect(page.getByTestId("admin-tab-evaluation")).toBeVisible();
  await page.getByRole("tab", { name: "Exam results" }).click();
  await expect(page.getByRole("heading", { name: "Official Recall@10" })).toBeVisible();
  await page.getByRole("button", { name: "Run development exam" }).click();
  await expect(page.getByText(/development exam queued/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/development exam (queued|running|succeeded)/)).toBeVisible();
  await expect(
    page.getByText("All required gold chunks in the production Hybrid top 10: 2 of 2 (100%)"),
  ).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/SECRET_QUESTION/)).toHaveCount(0);
});

test("stubbed owner Evaluation review queue hides private text until a case is opened", async ({
  page,
  request,
}) => {
  await signInLiveMember(page, request);
  const documentId = "22222222-2222-4222-8222-222222222222";
  const chunkId = "33333333-3333-4333-8333-333333333333";
  await page.route("**/api/meta", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        api_version: "1",
        sse_schema_version: "1",
        min_client_version: "0.1.0",
        pdf_eval_workspace: true,
      }),
    });
  });
  await page.route("**/me", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "owner-e2e",
        role: "owner",
        authorization_version: 1,
        upload_enabled: true,
      }),
    });
  });
  await page.route("**/admin/graph/entity-rules**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rules: [] }),
    });
  });
  await page.route("**/documents**", async (route) => {
    if (route.request().method() !== "GET") {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          document_id: documentId,
          title: "Hybrid guide",
          visibility: "company",
          current_version_id: "11111111-1111-4111-8111-111111111111",
          visibility_generation: 1,
          created_at: null,
        },
      ]),
    });
  });
  await page.route("**/admin/pdf-eval/**", async (route) => {
    const url = route.request().url();
    const method = route.request().method();
    const json = (body: unknown, status = 200) =>
      route.fulfill({
        status,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
    if (method === "GET" && url.includes("/admin/pdf-eval/status")) {
      await json({
        enabled: true,
        case_count: 1,
        revision: null,
        approved_count: 0,
        draft_count: 1,
        rejected_count: 0,
        stale_gold_count: 0,
        live_count: 1,
        remaining_capacity: 59,
        dataset_present: true,
        holdout_opened: false,
      });
      return;
    }
    if (method === "GET" && url.includes("/admin/pdf-eval/passages")) {
      await json({
        items: [
          {
            chunk_id: chunkId,
            document_id: documentId,
            version_id: "11111111-1111-4111-8111-111111111111",
            page_number: 1,
            heading_path: ["Chapter 1"],
            raw_text: "Hybrid retrieval text",
          },
        ],
        next_chunk_id: null,
      });
      return;
    }
    if (method === "GET" && /\/admin\/pdf-eval\/cases\/case-e2e/.test(url)) {
      await json({
        revision: "1",
        case_id: "case-e2e",
        split: "development",
        query_class: "factual_definition",
        human_approved: false,
        generated_only: true,
        reviewer: null,
        expected_refusal: false,
        expected_scope: "unscoped",
        chunk_ids: [chunkId],
        page_numbers: [1],
        heading_paths: ["Chapter 1"],
        required_terms: ["Hybrid"],
        question: "SECRET_QUESTION_E2E",
        expected_answer: "SECRET_ANSWER_E2E",
        atomic_facts: ["Agents coordinate tools."],
        review_status: "draft",
        source_family_id: null,
        source_run_id: null,
        document_id: documentId,
        version_id: "11111111-1111-4111-8111-111111111111",
        gold: [
          {
            ordinal: 1,
            chunk_id: chunkId,
            document_id: documentId,
            version_id: "11111111-1111-4111-8111-111111111111",
            page_number: 1,
            page_label: "1",
            section_path: ["Chapter 1"],
            stale: false,
          },
        ],
        gold_stale: false,
        reviewer_user_id: null,
        row_version: 1,
      });
      return;
    }
    if (method === "GET" && /\/admin\/pdf-eval\/cases(\?|$)/.test(url)) {
      await json({
        revision: "",
        items: [
          {
            case_id: "case-e2e",
            split: "development",
            query_class: "factual_definition",
            human_approved: false,
            generated_only: true,
            reviewer: null,
            expected_refusal: false,
            gold_chunk_count: 1,
            review_status: "draft",
            source_family_id: null,
            gold_stale: false,
            row_version: 1,
          },
        ],
        next_case_id: null,
      });
      return;
    }
    if (method === "GET" && url.includes("/admin/pdf-eval/reports/latest")) {
      await json({
        present: false,
        holdout_opened: false,
        exam_run_id: null,
        split: "development",
        dataset_hash: null,
        case_count: null,
        hit_count: null,
        hybrid_recall_at_10: null,
        gates_pass: null,
        created_at: null,
      });
      return;
    }
    await route.continue();
  });
  await page.goto("/admin?tab=evaluation");
  await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible();
  await page.getByRole("tab", { name: "Review cases" }).click();
  const queue = page.getByRole("navigation", { name: "Evaluation cases" });
  await expect(queue.getByText("Factual definition")).toBeVisible();
  await expect(queue.getByText("SECRET_QUESTION_E2E")).toHaveCount(0);
  await expect(queue.getByText("SECRET_ANSWER_E2E")).toHaveCount(0);
  await queue.getByRole("button", { name: /Factual definition/ }).click();
  await expect(page.getByRole("textbox", { name: "Question", exact: true })).toHaveValue("SECRET_QUESTION_E2E");
  await expect(page.getByRole("heading", { name: "Required source passages" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Test this case" })).toBeVisible();
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
