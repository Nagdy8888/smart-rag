import { describe, expect, it } from "vitest";
import { isAnswerTable, parseAnswerTable } from "./answer-table";

describe("answer tables", () => {
  it("parses a Markdown pipe table with a caption", () => {
    const text = [
      "Table 2-1 Selected models",
      "| Model | Maintainer | MMLU |",
      "| --- | --- | --- |",
      "| Llama 3.1 | Meta | 56.1 |",
      "| Gemma 2 | Google | 72.1 |",
    ].join("\n");
    expect(isAnswerTable(text)).toBe(true);
    const table = parseAnswerTable(text);
    expect(table?.caption).toBe("Table 2-1 Selected models");
    expect(table?.headers).toEqual(["Model", "Maintainer", "MMLU"]);
    expect(table?.rows).toEqual([
      ["Llama 3.1", "Meta", "56.1"],
      ["Gemma 2", "Google", "72.1"],
    ]);
    expect(table?.preformatted).toBeUndefined();
  });

  it("parses multi-space column rows without pipes", () => {
    const text = [
      "Table 8-2 Throughput",
      "Model  Maintainer  Tokens",
      "Alpha  Acme         120",
      "Beta   Other        95",
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.headers).toEqual(["Model", "Maintainer", "Tokens"]);
    expect(table?.rows).toEqual([
      ["Alpha", "Acme", "120"],
      ["Beta", "Other", "95"],
    ]);
  });

  it("parses single-space Table N-M salvage rows into an HTML grid", () => {
    const text = [
      "Table 2-1. Selected open weight models by performance and size",
      "Model Maintainer MMLU Parameters (billion)",
      "Llama 3.1 Instruct Turbo Meta 56.1 8 20 RTX 3090",
      "Gemma 2 Google 72.1 9 22.5 RTX 3090",
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.caption).toMatch(/Table 2-1/);
    expect(table?.preformatted).toBeUndefined();
    expect(table?.rows).toEqual([
      ["Llama 3.1 Instruct Turbo", "Meta", "56.1", "8", "20", "RTX 3090"],
      ["Gemma 2", "Google", "72.1", "9", "22.5", "RTX 3090"],
    ]);
  });

  it("keeps ambiguous caption bodies as preformatted when metric rows are missing", () => {
    const text = [
      "Table 2-1. Selected open weight models by performance and size",
      "Model Maintainer MMLU Parameters (billion)",
      "VRAM (full precision model in GB)",
      "Sample hardware required for local inference",
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.caption).toMatch(/Table 2-1/);
    expect(table?.preformatted).toContain("Sample hardware required");
  });

  it("parses a collapsed single-line pipe table from Ask answers", () => {
    const text =
      "| Approach | Pros | Cons | Best for | |----------|------|------|---------| | Relational databases (e.g., PostgreSQL/Redis) | Flexible, queryable, cost-effective | Manual management, potential inconsistency | Custom, high-query systems | | Vector stores (e.g., Pinecone) | Semantic search, scalable embeddings | Higher cost, specialized setup | Knowledge-intensive agents |";
    expect(isAnswerTable(text)).toBe(true);
    const table = parseAnswerTable(text);
    expect(table?.headers).toEqual(["Approach", "Pros", "Cons", "Best for"]);
    expect(table?.rows).toEqual([
      [
        "Relational databases (e.g., PostgreSQL/Redis)",
        "Flexible, queryable, cost-effective",
        "Manual management, potential inconsistency",
        "Custom, high-query systems",
      ],
      [
        "Vector stores (e.g., Pinecone)",
        "Semantic search, scalable embeddings",
        "Higher cost, specialized setup",
        "Knowledge-intensive agents",
      ],
    ]);
    expect(table?.preformatted).toBeUndefined();
  });

  it("strips prose before a titled Table N-M. caption", () => {
    const text = [
      "In Table 2-1, a small selection of language models are shown.",
      "Table 2-1. Selected open weight models by performance and size",
      "Model  Maintainer  MMLU",
      "Llama  Meta         56.1",
      "Gemma  Google       72.1",
      "22 | Chapter 2: Designing Agent Systems",
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.caption).toMatch(/^Table 2-1\./);
    expect(table?.headers).toEqual(["Model", "Maintainer", "MMLU"]);
    expect(table?.rows).toEqual([
      ["Llama", "Meta", "56.1"],
      ["Gemma", "Google", "72.1"],
    ]);
    expect(table?.preformatted).toBeUndefined();
  });

  it("rejects ordinary prose", () => {
    expect(isAnswerTable("The refund period is 30 days.")).toBe(false);
    expect(parseAnswerTable("Just one pipe | leftover")).toBeNull();
  });

  it("parses a salvage RACI matrix (Table 10-3) into an HTML grid", () => {
    const text = [
      "Table 10-3. RACI matrix of monitoring metrics and cross-functional responsibilities",
      "Metric/activity Product team ML engineers Infra/SRE team Latency (e.g., planning or tool call delays)",
      "A (owns user impact) / C (consults on UX thresholds)",
      "R (optimizes prompts/ models) / I (informed on regressions)",
      "R (monitors infra causes) / C (consults on scaling)",
      " call delays)",
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
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.preformatted).toBeUndefined();
    expect(table?.caption).toMatch(/Table 10-3/);
    expect(table?.headers).toEqual([
      "Metric/activity",
      "Product team",
      "ML engineers",
      "Infra/SRE team",
    ]);
    expect(table?.rows.length).toBeGreaterThanOrEqual(3);
    expect(table?.rows[0]?.[0]).toMatch(/Latency/i);
    expect(table?.rows[0]?.[1]).toMatch(/owns user impact/i);
    const hallucination = table?.rows.find((row) =>
      /Hallucination rates/i.test(row[0] ?? ""),
    );
    expect(hallucination?.[2]).toMatch(/detection/i);
    // OCR duplicate of the Latency trio must not create a second identical row.
    const latencyRows = table?.rows.filter((row) => /Latency/i.test(row[0] ?? "")) ?? [];
    expect(latencyRows).toHaveLength(1);
    expect(
      table?.rows.some((row) => /^\s*call delays\)/i.test(row[0] ?? "")),
    ).toBe(false);
    expect(table?.rows).toHaveLength(4);
  });

  it("parses a collapsed pipe table without a separator row", () => {
    const text =
      "| Model | Score | Size | Llama | 56.1 | 8B | Gemma | 72.1 | 9B |";
    const table = parseAnswerTable(text);
    expect(table?.preformatted).toBeUndefined();
    expect(table?.headers).toEqual(["Model", "Score", "Size"]);
    expect(table?.rows).toEqual([
      ["Llama", "56.1", "8B"],
      ["Gemma", "72.1", "9B"],
    ]);
  });

  it("unwraps a saved Item/Detail grid that labeled lines Row N", () => {
    const text = [
      "Table 4-2. Recorded lines",
      "| Item | Detail |",
      "| --- | --- |",
      "| Row 1 | Header line kept as its own row |",
      "| First cell | Second cell |",
      "| Third cell | Fourth cell |",
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.caption).toMatch(/Table 4-2/);
    expect(table?.headers).toEqual([]);
    expect(table?.preformatted).toBe(
      [
        "Header line kept as its own row",
        "First cell",
        "Second cell",
        "Third cell",
        "Fourth cell",
      ].join("\n"),
    );
  });

  it("keeps hostile markup as plain cell text", () => {
    const text = [
      "| Name | Payload |",
      "| --- | --- |",
      "| safe | <img src=x onerror=alert(1)> |",
    ].join("\n");
    const table = parseAnswerTable(text);
    expect(table?.rows[0]?.[1]).toBe("<img src=x onerror=alert(1)>");
  });
});
