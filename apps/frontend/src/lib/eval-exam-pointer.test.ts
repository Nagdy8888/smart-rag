// @vitest-environment jsdom

import { afterEach, describe, expect, it } from "vitest";
import {
  EVAL_EXAM_POINTER_KEY,
  clearEvalExamPointer,
  parseEvalExamPointer,
  readEvalExamPointer,
  writeEvalExamPointer,
} from "./eval-exam-pointer";

describe("eval exam pointer", () => {
  afterEach(() => {
    sessionStorage.clear();
  });

  it("stores only exam id and split", () => {
    writeEvalExamPointer({ examRunId: "exam-1", split: "development" });
    const raw = sessionStorage.getItem(EVAL_EXAM_POINTER_KEY);
    expect(raw).not.toBeNull();
    expect(raw).not.toContain("question");
    expect(raw).not.toContain("answer");
    expect(parseEvalExamPointer(raw)).toEqual({
      examRunId: "exam-1",
      split: "development",
    });
    expect(readEvalExamPointer()).toEqual({
      examRunId: "exam-1",
      split: "development",
    });
  });

  it("ignores malformed payloads and holdout splits", () => {
    expect(parseEvalExamPointer("not-json")).toBeNull();
    expect(
      parseEvalExamPointer(
        JSON.stringify({ examRunId: "exam-1", split: "holdout" }),
      ),
    ).toBeNull();
    expect(parseEvalExamPointer(JSON.stringify({ split: "development" }))).toBeNull();
    writeEvalExamPointer({ examRunId: "exam-1", split: "qualification" });
    clearEvalExamPointer();
    expect(readEvalExamPointer()).toBeNull();
  });
});
