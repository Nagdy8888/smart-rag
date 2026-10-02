/**
 * Canned answer texts for the Ask empty-state format gallery.
 *
 * Each sample is shaped like a verified assistant paragraph so the live
 * code / table / prose renderers can be inspected without calling Ask.
 */

export type AnswerFormatSampleId =
  | "code"
  | "table"
  | "raci"
  | "prose"
  | "mixed";

export type AnswerFormatSample = {
  /** Stable tab id. */
  id: AnswerFormatSampleId;
  /** Short chip label in the gallery. */
  label: string;
  /** One-line description under the tabs. */
  blurb: string;
  /** Assistant answer body (paragraphs separated by blank lines). */
  answer: string;
};

/**
 * Format samples shown in the empty Ask column.
 *
 * Order is the default tab order. Content is synthetic and safe to ship.
 */
export const ANSWER_FORMAT_SAMPLES: readonly AnswerFormatSample[] = [
  {
    id: "code",
    label: "Code",
    blurb: "Fenced Python with language header and Copy.",
    answer: [
      "Here is the tool definition as a fenced block:",
      ["```python", "def cancel_order(order_id: str) -> str:", '    """Cancel an order that hasn\'t shipped."""', "    return f\"cancelled:{order_id}\"", "```"].join(
        "\n",
      ),
    ].join("\n\n"),
  },
  {
    id: "table",
    label: "Table",
    blurb: "Markdown pipe table as a real HTML grid.",
    answer: [
      "Selected open-weight models:",
      [
        "| Model | Score | Size |",
        "| --- | ---: | --- |",
        "| Llama 3.1 Instruct Turbo | 56.1 | 8B |",
        "| Gemma 2 | 72.1 | 9B |",
        "| Qwen2.5 | 68.4 | 14B |",
      ].join("\n"),
    ].join("\n\n"),
  },
  {
    id: "raci",
    label: "RACI",
    blurb: "Salvage-style RACI matrix (Table 10-3 shape) without OCR junk rows.",
    answer: [
      "Table 10-3. RACI matrix of monitoring metrics and cross-functional responsibilities",
      "Metric/activity Product team ML engineers Infra/SRE team Latency (e.g., planning or tool call delays)",
      "A (owns user impact) / C (consults on UX thresholds)",
      "R (optimizes prompts/ models) / I (informed on regressions)",
      "R (monitors infra causes) / C (consults on scaling)",
      "Hallucination rates C (provides user feedback context) / I (informed on trends)",
      "A/R (owns detection/ mitigation via evals)",
      "I (informed for alerting setup)",
      "Task success rate A (owns product goals) / R (defines success criteria)",
      "C (consults on model improvements)",
      "I (informed for system reliability ties)",
      "Token usage/cost C (consults on business impact) R (optimizes generations) / I (informed on spikes)",
      "A (owns budgeting/scaling) / R (monitors infra efficiency)",
    ].join("\n"),
  },
  {
    id: "prose",
    label: "Prose",
    blurb: "Bold, inline code, and lists — not raw Markdown markers.",
    answer: [
      "The **refund window** is 30 days. Call `POST /v1/refunds` when filing a claim.",
      ["- Collect order id", "- Verify shipment status", "- Issue refund if eligible"].join(
        "\n",
      ),
      ["1. Authenticate", "2. Create conversation", "3. Stream the answer"].join("\n"),
    ].join("\n\n"),
  },
  {
    id: "mixed",
    label: "Mixed",
    blurb: "Prose, code, and a table in one answer.",
    answer: [
      "Use this **ping** helper, then compare stacks:",
      ["```python", "def ping() -> str:", '    return "pong"', "```"].join("\n"),
      [
        "| Stack | Focus |",
        "| --- | --- |",
        "| Langfuse | LLM tracing |",
        "| SigNoz | Infra observability |",
      ].join("\n"),
      "Keep timeouts short and log failures with `error_code`.",
    ].join("\n\n"),
  },
] as const;

/**
 * Look up one format sample by id.
 *
 * @param id - Sample id from the gallery tabs.
 * @returns Matching sample, or the first sample when unknown.
 */
export function answerFormatSample(
  id: AnswerFormatSampleId | string,
): AnswerFormatSample {
  return (
    ANSWER_FORMAT_SAMPLES.find((sample) => sample.id === id) ??
    ANSWER_FORMAT_SAMPLES[0]!
  );
}
