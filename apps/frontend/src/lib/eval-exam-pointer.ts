/**
 * Resume pointer for an in-flight hosted exam. sessionStorage only.
 */

/** sessionStorage key for the active exam pointer. */
export const EVAL_EXAM_POINTER_KEY = "smart-rag.eval-exam-pointer";

/** Durable resume pointer. No questions, answers, or ranked IDs. */
export type EvalExamPointer = {
  examRunId: string;
  split: "development" | "qualification";
};

/**
 * Parse a stored exam pointer.
 *
 * @param raw - Stored JSON, or null.
 * @returns Pointer, or null when missing or malformed.
 */
export function parseEvalExamPointer(raw: string | null): EvalExamPointer | null {
  if (raw === null || raw === "") {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(raw);
    if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
      return null;
    }
    const record = parsed as Record<string, unknown>;
    const examRunId = String(record.examRunId ?? "");
    const split = record.split;
    if (
      examRunId === "" ||
      (split !== "development" && split !== "qualification")
    ) {
      return null;
    }
    return { examRunId, split };
  } catch {
    return null;
  }
}

/**
 * Read the exam pointer from sessionStorage.
 *
 * @param storage - sessionStorage, or null when unavailable.
 * @returns Pointer, or null.
 */
export function readEvalExamPointer(
  storage: Pick<Storage, "getItem"> | null = defaultSessionStorage(),
): EvalExamPointer | null {
  if (storage === null) {
    return null;
  }
  try {
    return parseEvalExamPointer(storage.getItem(EVAL_EXAM_POINTER_KEY));
  } catch {
    return null;
  }
}

/**
 * Persist the exam pointer. Never writes private case text.
 *
 * @param pointer - Exam id and split.
 * @param storage - sessionStorage, or null when unavailable.
 */
export function writeEvalExamPointer(
  pointer: EvalExamPointer,
  storage: Pick<Storage, "setItem"> | null = defaultSessionStorage(),
): void {
  if (storage === null) {
    return;
  }
  try {
    storage.setItem(
      EVAL_EXAM_POINTER_KEY,
      JSON.stringify({
        examRunId: pointer.examRunId,
        split: pointer.split,
      }),
    );
  } catch {
    return;
  }
}

/**
 * Clear the exam pointer after a terminal exam or explicit dismiss.
 *
 * @param storage - sessionStorage, or null when unavailable.
 */
export function clearEvalExamPointer(
  storage: Pick<Storage, "removeItem"> | null = defaultSessionStorage(),
): void {
  if (storage === null) {
    return;
  }
  try {
    storage.removeItem(EVAL_EXAM_POINTER_KEY);
  } catch {
    return;
  }
}

/**
 * Return sessionStorage when the browser exposes it.
 *
 * @returns sessionStorage, or null in non-browser tests without it.
 */
function defaultSessionStorage(): Storage | null {
  if (typeof sessionStorage === "undefined") {
    return null;
  }
  return sessionStorage;
}
