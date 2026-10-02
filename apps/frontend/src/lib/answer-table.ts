/**
 * Display-only detectors and parsers for verified answer table paragraphs.
 *
 * Stored answer text is unchanged. Cell strings stay plain text for React
 * text nodes — never HTML.
 */

export type AnswerTableModel = {
  caption?: string;
  headers: string[];
  rows: string[][];
  /**
   * When column structure is ambiguous (common for OCR/book salvage),
   * keep the body as preformatted lines under the caption.
   */
  preformatted?: string;
};

const PIPE_SEP = /^\s*\|?(?:\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?\s*$/;
const TABLE_CAPTION = /\bTable\s+\d+-\d+\b/i;
const MULTI_SPACE = /\s{2,}|\t+/;

/**
 * Return whether a verified paragraph should render as a table.
 *
 * @param text - One verified paragraph.
 * @returns True for pipe Markdown, caption/column, or Table N-M blocks.
 */
export function isAnswerTable(text: string): boolean {
  return parseAnswerTable(text) !== null;
}

/**
 * Parse a pipe, whitespace-column, or caption-preformatted table block.
 *
 * @param text - One verified paragraph.
 * @returns Structured rows (or preformatted body), or null when not tabular.
 */
export function parseAnswerTable(text: string): AnswerTableModel | null {
  const source = normalizeTableSource(text.replace(/\r\n/g, "\n").trim());
  if (!source) {
    return null;
  }
  return (
    parsePipeTable(source) ??
    parseColumnTable(source) ??
    parseMetricSpaceTable(source) ??
    parseRaciMatrixTable(source) ??
    parseCaptionBlock(source)
  );
}

/**
 * Prefer the titled caption and drop chapter footers from salvage text.
 *
 * @param source - Normalized paragraph text.
 * @returns Cleaner table candidate text.
 */
function normalizeTableSource(source: string): string {
  let text = source.trim();
  const title = text.match(/\bTable\s+\d+-\d+\.[^\n]*/i);
  if (title?.index !== undefined && title.index > 0) {
    text = text.slice(title.index);
  }
  text = text.replace(/(?:\n|^)\s*\d+\s*\|\s*Chapter\s+\d+[\s\S]*$/i, "");
  return text.trim();
}

/** Inline GFM separator row, used when pipe tables arrive with newlines stripped. */
const PIPE_SEP_INLINE = /\|(?:\s*:?-+:?\s*\|)+(?:\s*:?-+:?\s*)?\|?/;

/**
 * Parse a GitHub-flavored pipe table when present.
 *
 * Collapsed single-line answers (header + separator + rows jammed together)
 * are expanded before the line-oriented parse so Ask still renders an HTML
 * table instead of a prose paragraph of pipes.
 *
 * @param source - Normalized paragraph text.
 * @returns Table model, or null.
 */
function parsePipeTable(source: string): AnswerTableModel | null {
  const expanded =
    expandCollapsedPipeSource(source) ?? expandEqualWidthPipeSource(source);
  const working = expanded ?? source;
  const lines = working
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 2) {
    return null;
  }
  let caption: string | undefined;
  let start = 0;
  if (TABLE_CAPTION.test(lines[0] ?? "") && !lines[0]?.includes("|")) {
    caption = lines[0];
    start = 1;
  }
  const body = lines.slice(start);
  const pipeRows = body.filter((line) => line.includes("|"));
  if (pipeRows.length < 2) {
    return null;
  }
  const sepIndex = body.findIndex((line) => PIPE_SEP.test(line));
  const dataLines =
    sepIndex >= 0
      ? body.filter((line, index) => index !== sepIndex && line.includes("|"))
      : pipeRows;
  if (dataLines.length < 2) {
    return null;
  }
  const cells = dataLines.map(splitPipeCells);
  const width = Math.max(...cells.map((row) => row.length));
  if (width < 2) {
    return null;
  }
  const normalized = cells.map((row) => padRow(row, width));
  return {
    caption,
    headers: normalized[0] ?? [],
    rows: normalized.slice(1),
  };
}

/**
 * Expand a single-line pipe table that has no Markdown separator row.
 *
 * Uses the first pipe row's cell count as the width and chunks remaining
 * cells into rows so Ask answers without `|---|` still become HTML tables.
 *
 * @param source - Normalized paragraph that may already be multiline.
 * @returns Multiline GFM text, or null when width cannot be inferred.
 */
function expandEqualWidthPipeSource(source: string): string | null {
  const pipeLines = source
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.includes("|"));
  if (pipeLines.length >= 2) {
    return null;
  }
  if (PIPE_SEP_INLINE.test(source)) {
    return null;
  }
  let working = source.trim();
  let caption: string | undefined;
  const captionMatch = working.match(/^(.*?\bTable\s+\d+-\d+\b[^\|]*)\|/i);
  if (captionMatch) {
    caption = captionMatch[1]?.trim();
    working = working.slice(captionMatch[1]?.length ?? 0).trim();
  }
  if (!working.includes("|")) {
    return null;
  }
  const tokens = working
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim())
    .filter((cell, index, all) => !(cell === "" && (index === 0 || index === all.length - 1)));
  // Drop empty tokens that only mark row boundaries between pipes: `| a | | b |`
  // is uncommon; keep consecutive non-empty cells and infer width from the
  // first run until we see a repeated header-like break. Prefer width >= 2
  // that divides the token count with a header + at least one data row.
  const dense = tokens.filter((cell) => cell !== "");
  if (dense.length < 4) {
    return null;
  }
  let width = 0;
  for (let candidate = 2; candidate <= Math.min(8, Math.floor(dense.length / 2)); candidate += 1) {
    if (dense.length % candidate === 0) {
      width = candidate;
      break;
    }
  }
  if (width < 2) {
    // Fall back: assume first row ends when we have seen enough cells and
    // remaining length is a multiple of that width.
    for (let candidate = Math.min(6, Math.floor(dense.length / 2)); candidate >= 2; candidate -= 1) {
      if ((dense.length - candidate) % candidate === 0 && dense.length - candidate >= candidate) {
        width = candidate;
        break;
      }
    }
  }
  if (width < 2) {
    return null;
  }
  const rows: string[][] = [];
  for (let i = 0; i < dense.length; i += width) {
    rows.push(padRow(dense.slice(i, i + width), width));
  }
  if (rows.length < 2) {
    return null;
  }
  const headers = rows[0] ?? [];
  const body = rows.slice(1);
  return [
    ...(caption ? [caption] : []),
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...body.map((row) => `| ${row.join(" | ")} |`),
  ].join("\n");
}

/**
 * Expand a pipe table that lost its newlines into one GFM line per row.
 *
 * Ask answers sometimes return `| h1 | h2 | |---|---| | r1 | r2 |` on a single
 * line. Splitting on `\\n` alone cannot see the rows; the separator row is the
 * reliable anchor.
 *
 * @param source - Normalized paragraph that may already be multiline.
 * @returns Multiline GFM text, or null when no inline separator is present.
 */
function expandCollapsedPipeSource(source: string): string | null {
  const pipeLines = source
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.includes("|"));
  if (pipeLines.length >= 2) {
    return null;
  }
  const sepMatch = source.match(PIPE_SEP_INLINE);
  if (!sepMatch || sepMatch.index === undefined) {
    return null;
  }
  let before = source.slice(0, sepMatch.index).trim();
  const after = source.slice(sepMatch.index + sepMatch[0].length).trim();
  let caption: string | undefined;
  const captionMatch = before.match(/^(.*?\bTable\s+\d+-\d+\b[^\|]*)\|/i);
  if (captionMatch) {
    caption = captionMatch[1]?.trim();
    before = before.slice(captionMatch[1]?.length ?? 0).trim();
  } else if (TABLE_CAPTION.test(before) && !before.includes("|")) {
    caption = before;
    before = "";
  }
  if (!before.includes("|")) {
    return null;
  }
  const headers = splitPipeCells(before);
  const width = headers.length;
  if (width < 2) {
    return null;
  }
  const tokens = after
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
  const rows: string[][] = [];
  let current: string[] = [];
  for (const token of tokens) {
    if (token === "" && current.length > 0) {
      rows.push(padRow(current, width));
      current = [];
      continue;
    }
    if (token === "") {
      continue;
    }
    current.push(token);
    if (current.length === width) {
      rows.push(current);
      current = [];
    }
  }
  if (current.length > 0) {
    rows.push(padRow(current, width));
  }
  if (rows.length < 1) {
    return null;
  }
  const lines = [
    ...(caption ? [caption] : []),
    `| ${headers.join(" | ")} |`,
    `| ${headers.map(() => "---").join(" | ")} |`,
    ...rows.map((row) => `| ${row.join(" | ")} |`),
  ];
  return lines.join("\n");
}

/**
 * Parse caption-plus-whitespace-column blocks with clear column gaps.
 *
 * @param source - Normalized paragraph text.
 * @returns Table model, or null.
 */
function parseColumnTable(source: string): AnswerTableModel | null {
  const lines = source
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim());
  if (lines.length < 3) {
    return null;
  }
  let caption: string | undefined;
  let start = 0;
  const first = lines[0]?.trim() ?? "";
  if (TABLE_CAPTION.test(first)) {
    caption = first;
    start = 1;
  } else if (!looksLikeColumnRow(first)) {
    return null;
  }
  const body = lines.slice(start).map((line) => line.trim());
  const columnRows = body.filter(looksLikeColumnRow);
  if (columnRows.length < 2) {
    return null;
  }
  if (!caption && columnRows.length < 3) {
    return null;
  }
  const cells = columnRows.map(splitColumnCells);
  const width = Math.max(...cells.map((row) => row.length));
  if (width < 3) {
    return null;
  }
  const normalized = cells.map((row) => padRow(row, width));
  return {
    caption,
    headers: normalized[0] ?? [],
    rows: normalized.slice(1),
  };
}

const PURE_NUMBER = /^-?\d+(?:[.,]\d+)?$/;
const DECIMAL_NUMBER = /^-?\d+[.,]\d+$/;

/**
 * Parse single-space book salvage rows that start metrics at a decimal score.
 *
 * Handles OCR lines such as ``Gemma 2 Google 72.1 9 22.5 RTX 3090`` where
 * multi-space column gaps are missing. Model names may include decimals
 * (``Llama 3.1``); metrics begin at the last decimal that still leaves two
 * trailing numeric cells.
 *
 * @param source - Normalized paragraph text.
 * @returns Table model with HTML rows, or null.
 */
function parseMetricSpaceTable(source: string): AnswerTableModel | null {
  const lines = source
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 3) {
    return null;
  }
  let caption: string | undefined;
  let start = 0;
  if (TABLE_CAPTION.test(lines[0] ?? "")) {
    caption = lines[0];
    start = 1;
  }
  const body = lines.slice(start);
  const parsed = body
    .map((line) => splitMetricSpaceRow(line))
    .filter((row): row is string[] => row !== null);
  if (parsed.length < 2) {
    return null;
  }
  const width = Math.max(...parsed.map((row) => row.length));
  if (width < 4) {
    return null;
  }
  const headers = [
    "Model",
    "Maintainer",
    ...Array.from({ length: width - 2 }, (_, index) => `Col ${index + 3}`),
  ];
  return {
    caption,
    headers: padRow(headers, width),
    rows: parsed.map((row) => padRow(row, width)),
  };
}

/**
 * Split one single-space metric row into model / maintainer / numeric cells.
 *
 * @param line - Candidate data line.
 * @returns Cell strings, or null when the line is not metric-shaped.
 */
function splitMetricSpaceRow(line: string): string[] | null {
  const tokens = line.trim().split(/\s+/).filter(Boolean);
  if (tokens.length < 5) {
    return null;
  }
  const decimalIndexes = tokens
    .map((token, index) => (DECIMAL_NUMBER.test(token) ? index : -1))
    .filter((index) => index >= 0);
  if (decimalIndexes.length === 0) {
    return null;
  }
  let metricStart = -1;
  for (let i = decimalIndexes.length - 1; i >= 0; i -= 1) {
    const index = decimalIndexes[i] ?? -1;
    if (index < 2) {
      continue;
    }
    const trailingNums = tokens
      .slice(index + 1)
      .filter((token) => PURE_NUMBER.test(token)).length;
    if (trailingNums >= 2) {
      metricStart = index;
      break;
    }
  }
  if (metricStart < 2) {
    return null;
  }
  const labelTokens = tokens.slice(0, metricStart);
  const maintainer = labelTokens[labelTokens.length - 1] ?? "";
  const model = labelTokens.slice(0, -1).join(" ");
  if (!model || !maintainer || PURE_NUMBER.test(maintainer)) {
    return null;
  }
  const metrics: string[] = [];
  let cursor = metricStart;
  while (cursor < tokens.length && PURE_NUMBER.test(tokens[cursor] ?? "")) {
    metrics.push((tokens[cursor] ?? "").replace(",", "."));
    cursor += 1;
  }
  if (metrics.length < 3) {
    return null;
  }
  const hardware = tokens.slice(cursor).join(" ");
  return hardware
    ? [model, maintainer, ...metrics, hardware]
    : [model, maintainer, ...metrics];
}

/** One RACI role token such as ``A (owns…)`` or ``A/R (owns…)``. */
const RACI_ROLE = /[ACRI](?:\/[ACRI])?\s*\([^)]+\)/;
/** One matrix cell: one role, or two roles joined by `` / ``. */
const RACI_CELL = new RegExp(
  `${RACI_ROLE.source}(?:\\s*/\\s*${RACI_ROLE.source})?`,
  "g",
);
const RACI_HEADER =
  /^Metric\/activity\s+Product team\s+ML engineers\s+Infra\/SRE team(?:\s+(.+))?$/i;
const RACI_HEADERS = [
  "Metric/activity",
  "Product team",
  "ML engineers",
  "Infra/SRE team",
] as const;

/**
 * Parse book-salvage RACI matrices (Table 10-3 style) into an HTML grid.
 *
 * Salvage often has no pipes: the header and first metric share a line, then
 * each team cell is its own line (``A (…) / C (…)``). Duplicate OCR fragments
 * such as a lone ``call delays)`` plus a repeated cell trio are dropped.
 *
 * @param source - Normalized paragraph text.
 * @returns Table model with four columns, or null.
 */
function parseRaciMatrixTable(source: string): AnswerTableModel | null {
  const lines = source
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (lines.length < 4) {
    return null;
  }
  let caption: string | undefined;
  let start = 0;
  if (TABLE_CAPTION.test(lines[0] ?? "")) {
    caption = lines[0];
    start = 1;
  }
  const headerLine = lines[start] ?? "";
  const headerMatch = headerLine.match(RACI_HEADER);
  if (!headerMatch && !/Metric\/activity/i.test(headerLine)) {
    return null;
  }
  if (!/Product team/i.test(headerLine) || !/ML engineers/i.test(headerLine)) {
    return null;
  }
  const pendingMetric = (headerMatch?.[1] ?? "").trim();
  const bodyLines = lines.slice(start + 1);
  const rows: string[][] = [];
  let metric = pendingMetric;
  let cells: string[] = [];

  const flushRow = (): void => {
    if (!metric || cells.length === 0) {
      return;
    }
    const row = padRow([metric, ...cells], 4);
    const prior = rows[rows.length - 1];
    if (
      prior &&
      prior.length === row.length &&
      prior.every((cell, index) => cell === row[index])
    ) {
      metric = "";
      cells = [];
      return;
    }
    rows.push(row);
    metric = "";
    cells = [];
  };

  for (const line of bodyLines) {
    const extracted = extractRaciCells(line);
    if (extracted.cells.length === 0) {
      // OCR wrap fragments such as ``call delays)`` (often lowercase, paren-only).
      if (
        /\)\s*$/.test(line) &&
        !RACI_ROLE.test(line) &&
        (Boolean(metric) || /^[a-z]/.test(line))
      ) {
        continue;
      }
      if (line.length >= 3) {
        flushRow();
        metric = line;
      }
      continue;
    }
    if (extracted.metric) {
      flushRow();
      metric = extracted.metric;
      cells = [...extracted.cells];
    } else if (!metric) {
      // Orphan RACI trio after OCR wrap (no metric) — skip the duplicate.
      continue;
    } else {
      cells.push(...extracted.cells);
    }
    if (cells.length >= 3) {
      flushRow();
    }
  }
  flushRow();
  if (rows.length < 1) {
    return null;
  }
  return {
    caption,
    headers: [...RACI_HEADERS],
    rows,
  };
}

/**
 * Pull metric label and RACI cells from one salvage line.
 *
 * @param line - Body line after the header.
 * @returns Metric prefix (if any) and ordered RACI cell strings.
 */
function extractRaciCells(line: string): { metric: string; cells: string[] } {
  const cells: string[] = [];
  const re = new RegExp(RACI_CELL.source, "g");
  let match = re.exec(line);
  let firstIndex = -1;
  while (match) {
    if (firstIndex < 0) {
      firstIndex = match.index;
    }
    cells.push(match[0].replace(/\s+/g, " ").trim());
    match = re.exec(line);
  }
  if (cells.length === 0) {
    return { metric: "", cells: [] };
  }
  const metric = firstIndex > 0 ? line.slice(0, firstIndex).trim() : "";
  return { metric, cells };
}

/**
 * Fall back to a caption + preformatted body for Table N-M salvage text.
 *
 * Book chunks often use single spaces between columns, which cannot be
 * split reliably. Keeping the body in a pre block still reads as a table.
 *
 * @param source - Normalized paragraph text.
 * @returns Preformatted table model, or null.
 */
function parseCaptionBlock(source: string): AnswerTableModel | null {
  const lines = source
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim());
  if (lines.length < 3) {
    return null;
  }
  const first = lines[0]?.trim() ?? "";
  if (!TABLE_CAPTION.test(first)) {
    return null;
  }
  const body = lines
    .slice(1)
    .map((line) => line.trimEnd())
    .join("\n")
    .trim();
  if (!body) {
    return null;
  }
  return {
    caption: first,
    headers: [],
    rows: [],
    preformatted: body,
  };
}

/**
 * Split one Markdown pipe row into cell strings.
 *
 * @param line - Pipe-separated line.
 * @returns Cell texts.
 */
function splitPipeCells(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

/**
 * Split a whitespace/tab column row into cell strings.
 *
 * @param line - Multi-column line.
 * @returns Cell texts.
 */
function splitColumnCells(line: string): string[] {
  return line
    .trim()
    .split(MULTI_SPACE)
    .map((cell) => cell.trim())
    .filter(Boolean);
}

/**
 * Return whether a line looks like a multi-column data or header row.
 *
 * @param line - Candidate line.
 * @returns True when at least three column tokens are present.
 */
function looksLikeColumnRow(line: string): boolean {
  if (line.includes("|")) {
    return splitPipeCells(line).length >= 3;
  }
  return splitColumnCells(line).length >= 3;
}

/**
 * Pad a row to a fixed width with empty strings.
 *
 * @param row - Cell values.
 * @param width - Target column count.
 * @returns Padded row.
 */
function padRow(row: string[], width: number): string[] {
  if (row.length >= width) {
    return row.slice(0, width);
  }
  return [...row, ...Array.from({ length: width - row.length }, () => "")];
}
