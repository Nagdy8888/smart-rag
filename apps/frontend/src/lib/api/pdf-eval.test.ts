/**
 * Hosted PDF evaluation HTTP helper tests.
 */

import { describe, expect, it } from "vitest";
import type { ApiAuth } from "./headers";
import {
  deletePdfEvalCase,
  fetchPdfEvalExam,
  fetchPdfEvalLatestReport,
  listPdfEvalCases,
  listPdfEvalExamCases,
  listPdfEvalPassages,
  patchPdfEvalCase,
  regeneratePdfEvalDrafts,
  replacePdfEvalGold,
  setPdfEvalApproval,
  startPdfEvalExam,
} from "./pdf-eval";

const AUTH: ApiAuth = { accessToken: "jwt-token" };

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("pdf-eval admin clients", () => {
  it("lists cases with review_status and never holdout", async () => {
    const fetchImpl: typeof fetch = async (input) => {
      expect(String(input)).toContain("review_status=approved");
      expect(String(input)).not.toContain("holdout");
      return jsonResponse({ items: [], next_case_id: null });
    };
    await listPdfEvalCases(AUTH, fetchImpl, {
      split: "development",
      review_status: "approved",
      limit: 20,
    });
  });

  it("patches with expected_row_version instead of expected_revision", async () => {
    const fetchImpl: typeof fetch = async (_input, init) => {
      const payload = JSON.parse(String(init?.body)) as Record<string, unknown>;
      expect(payload.expected_row_version).toBe(3);
      expect(payload).not.toHaveProperty("expected_revision");
      expect(payload.question).toBe("What is Hybrid?");
      return jsonResponse({ case_id: "case-1", row_version: 4 });
    };
    const result = await patchPdfEvalCase(
      AUTH,
      "case-1",
      3,
      { question: "What is Hybrid?" },
      fetchImpl,
    );
    expect(result.row_version).toBe(4);
  });

  it("approves, replaces gold, and deletes with expected_row_version", async () => {
    let calls = 0;
    const fetchImpl: typeof fetch = async (_input, init) => {
      calls += 1;
      const payload = JSON.parse(String(init?.body)) as Record<string, unknown>;
      expect(payload.expected_row_version).toBe(1);
      expect(payload).not.toHaveProperty("expected_revision");
      return jsonResponse({ case_id: "case-1", row_version: 2 });
    };
    await setPdfEvalApproval(AUTH, "case-1", 1, true, fetchImpl);
    await replacePdfEvalGold(AUTH, "case-1", 1, ["chunk-1"], fetchImpl);
    await deletePdfEvalCase(AUTH, "case-1", 1, fetchImpl);
    expect(calls).toBe(3);
  });

  it("requires document_id on passages and regenerates by document", async () => {
    const fetchImpl: typeof fetch = async (input) => {
      const url = String(input);
      if (url.includes("/passages")) {
        expect(url).toContain("document_id=");
        return jsonResponse({ items: [], next_chunk_id: null });
      }
      return jsonResponse({ inserted_count: 2 });
    };
    await listPdfEvalPassages(
      AUTH,
      { documentId: "22222222-2222-4222-8222-222222222222", limit: 20 },
      fetchImpl,
    );
    const regen = await regeneratePdfEvalDrafts(
      AUTH,
      "22222222-2222-4222-8222-222222222222",
      fetchImpl,
    );
    expect(regen.inserted_count).toBe(2);
  });

  it("maps regenerate 409 capacity_exceeded", async () => {
    const fetchImpl: typeof fetch = async () =>
      jsonResponse({ detail: "capacity_exceeded" }, 409);
    await expect(
      regeneratePdfEvalDrafts(AUTH, "22222222-2222-4222-8222-222222222222", fetchImpl),
    ).rejects.toThrow("capacity_exceeded");
  });

  it("starts an exam with paid idempotency headers and omits an empty hash", async () => {
    const fetchImpl: typeof fetch = async (input, init) => {
      expect(String(input)).toContain("/admin/pdf-eval/exams");
      expect(init?.method).toBe("POST");
      const headers = init?.headers as Record<string, string>;
      expect(headers["Idempotency-Key"]).toBe("key-1");
      const payload = JSON.parse(String(init?.body)) as Record<string, unknown>;
      expect(payload.split).toBe("development");
      expect(payload.idempotency_key).toBe("key-1");
      expect(payload).not.toHaveProperty("expected_dataset_hash");
      return jsonResponse(
        {
          exam_run_id: "exam-1",
          status: "queued",
          dataset_hash: "abc",
          replayed: false,
          holdout_opened: false,
        },
        202,
      );
    };
    const result = await startPdfEvalExam(
      AUTH,
      { split: "development", idempotency_key: "key-1" },
      fetchImpl,
    );
    expect(result.exam_run_id).toBe("exam-1");
  });

  it("attaches empty_dataset counts and never a gates_pass field", async () => {
    const fetchImpl: typeof fetch = async () =>
      jsonResponse(
        {
          detail: "empty_dataset",
          draft_count: 2,
          approved_count: 0,
          rejected_count: 0,
          stale_gold_count: 1,
          live_count: 2,
        },
        422,
      );
    await expect(
      startPdfEvalExam(
        AUTH,
        { split: "development", idempotency_key: "key-1" },
        fetchImpl,
      ),
    ).rejects.toMatchObject({
      message: "empty_dataset",
      approved_count: 0,
      draft_count: 2,
      stale_gold_count: 1,
    });
  });

  it("maps exam 409 codes and reads present=false latest reports", async () => {
    const conflict: typeof fetch = async () =>
      jsonResponse({ detail: "already_running" }, 409);
    await expect(
      startPdfEvalExam(
        AUTH,
        { split: "development", idempotency_key: "key-1" },
        conflict,
      ),
    ).rejects.toThrow("already_running");
    const latest: typeof fetch = async (input) => {
      expect(String(input)).toContain("split=development");
      expect(String(input)).not.toContain("holdout");
      return jsonResponse({
        present: false,
        holdout_opened: false,
        exam_run_id: null,
        gates_pass: null,
      });
    };
    const report = await fetchPdfEvalLatestReport(AUTH, "development", latest);
    expect(report.present).toBe(false);
    expect(report.gates_pass).toBeNull();
    const exam: typeof fetch = async () =>
      jsonResponse({
        exam_run_id: "exam-1",
        split: "development",
        status: "running",
        dataset_hash: "abc",
        case_count: 2,
        completed_case_count: 1,
        holdout_opened: false,
        candidate_fingerprint: "def",
      });
    const status = await fetchPdfEvalExam(AUTH, "exam-1", exam);
    expect(status.completed_case_count).toBe(1);
    expect(status.candidate_fingerprint).toBe("def");
    const cases: typeof fetch = async () =>
      jsonResponse({
        exam_run_id: "exam-1",
        missed_count: 1,
        items: [
          {
            case_id: "case-1",
            ordinal: 1,
            hit: false,
            gold_count: 2,
            ranked_hit_count: 0,
          },
        ],
      });
    const listed = await listPdfEvalExamCases(AUTH, "exam-1", cases);
    expect(listed.items[0]?.hit).toBe(false);
    expect(JSON.stringify(listed)).not.toContain("question");
  });
});
