/**
 * Display-only formatting for verified answer paragraphs that contain source code.
 *
 * Stored answer text is unchanged. Rendering stays React text nodes.
 */

const DEF_PATTERN = /\b(?:async\s+)?def\s+\w+\s*\(/;
/** A class statement, not the word "class" inside a sentence. */
const CLASS_PATTERN = /\bclass\s+[A-Za-z_]\w*\s*(?:\([^)\n]*\))?\s*:/;
const TOOL_PATTERN = /@tool\b/;
const HEADER_PATTERN =
  /^((?:async\s+)?(?:def|class)\s+\w+\s*\([^)]*\)[^:]*):\s*([\s\S]*)$/;
/** Whole-paragraph fenced block (blank lines inside the body are allowed). */
const FENCE_WHOLE =
  /^\s*```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```[ \t]*\s*$/;
/** First fenced block anywhere in the paragraph. */
const FENCE_ANYWHERE =
  /```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]*?)\r?\n[ \t]*```/;
/** Opening fence without a closer — still show as code when body has source. */
const FENCE_OPEN_ONLY =
  /^\s*```([a-zA-Z0-9_+-]*)[ \t]*\r?\n([\s\S]+)$/;

export type CodeSnippetModel = {
  /** Formatted source for the code body. */
  code: string;
  /** Language label when known, else null. */
  language: string | null;
};

/**
 * Return sentence text when a fence only wraps prose.
 *
 * Source fences stay unchanged so the code box can still open them.
 *
 * @param text - One verified paragraph.
 * @returns Inner sentences, or the original text.
 */
export function proseFromDecorativeFence(text: string): string {
  const source = text.replace(/\r\n/g, "\n");
  const whole = source.match(FENCE_WHOLE);
  const anywhere = whole ?? source.match(FENCE_ANYWHERE);
  const openOnly = anywhere ?? source.match(FENCE_OPEN_ONLY);
  if (!openOnly) {
    return text;
  }
  const body = (openOnly[2] ?? "")
    .replace(/\n?[ \t]*```[ \t]*\s*$/, "")
    .replace(/\n+$/, "")
    .replace(/^\n+/, "");
  if (!body.trim() || !looksLikeProse(body)) {
    return text;
  }
  return body;
}

/**
 * Return whether a verified paragraph contains a function, class, or fence.
 *
 * @param text - One verified paragraph (prefer decoded).
 * @returns True when a definition, `@tool`, or source fence is present.
 * A sentence that only uses the word "class" stays prose.
 */
export function isCodeSnippet(text: string): boolean {
  if (extractFencedCode(text) !== null) {
    return true;
  }
  return DEF_PATTERN.test(text) || CLASS_PATTERN.test(text) || TOOL_PATTERN.test(text);
}

/** A full line that starts a source listing, not a sentence that mentions code. */
const SOURCE_LINE =
  /^(?:from\s+\S+(?:\s+import\b.*)?|import\s+\S+|(?:async\s+)?def\s+\w+|class\s+\w+|@\w+\b)$/;

export type SourceListingSplit = {
  /** Sentences before the listing. Empty when the paragraph is only source. */
  prose: string;
  /** Listing body with original line breaks. */
  code: string;
  /** Language label when the listing looks like Python, else null. */
  language: string | null;
};

/**
 * Split a trailing import or definition listing off a prose paragraph.
 *
 * A listing needs at least two source lines. Wrapped import tails stay in
 * the listing. A lone line number between those lines is left out. A
 * sentence that only mentions an import stays prose.
 *
 * @param text - One verified paragraph.
 * @returns Prose prefix and listing, or null when the paragraph is not a listing.
 */
export function splitTrailingSourceListing(text: string): SourceListingSplit | null {
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let start = -1;
  for (let index = 0; index < lines.length; index += 1) {
    if (SOURCE_LINE.test(lines[index]?.trim() ?? "")) {
      start = index;
      break;
    }
  }
  if (start < 0) {
    return null;
  }
  const tail = lines.slice(start);
  let previous = "";
  let sourceHits = 0;
  for (const line of tail) {
    if (!line.trim()) {
      continue;
    }
    const trimmed = line.trim();
    if (/^\d{1,4}$/.test(trimmed)) {
      continue;
    }
    if (SOURCE_LINE.test(trimmed)) {
      sourceHits += 1;
      previous = line;
      continue;
    }
    if (previous !== "" && isListingContinuation(line, previous)) {
      previous = line;
      continue;
    }
    return null;
  }
  if (sourceHits < 2) {
    return null;
  }
  const code = tail
    .filter((line) => !/^\d{1,4}$/.test(line.trim()))
    .join("\n")
    .trim();
  return {
    prose: lines.slice(0, start).join("\n").trim(),
    code,
    language: code
      .split("\n")
      .some((line) => SOURCE_LINE.test(line.trim()))
      ? "python"
      : null,
  };
}

/**
 * Return whether a line continues the previous source line.
 *
 * @param line - Current line, including leading spaces.
 * @param previous - Previous non-empty source line.
 * @returns True for an indent, a trailing comma, or an identifier tail.
 */
function isListingContinuation(line: string, previous: string): boolean {
  const current = line.trim();
  const prior = previous.trimEnd();
  if (current === "" || prior === "") {
    return false;
  }
  if (/^\s+\S/.test(line)) {
    return true;
  }
  if (/[,\\(]$/.test(prior)) {
    return true;
  }
  return /^[A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)*,?$/.test(current);
}

/**
 * Return display code and an optional language label for a code paragraph.
 *
 * @param text - Paragraph that mixes a sentence with source code or a fence.
 * @returns Snippet model for the CodeBlock UI. Not a new stored answer.
 */
export function formatCodeSnippetModel(text: string): CodeSnippetModel {
  const fenced = extractFencedCode(text);
  if (fenced !== null) {
    return fenced;
  }
  const code = formatCodeSnippet(text);
  return {
    code,
    language: inferLanguageFromSalvage(code),
  };
}

/**
 * Return only the function or class, with the docstring and return on their own lines.
 *
 * Multiline salvage bodies keep their newlines. Compacted one-liners still go
 * through the legacy reformatter. The split follows the signature colon after
 * the parameter list, so type hints inside the parentheses stay on the `def`
 * line.
 *
 * @param text - Paragraph that mixes a sentence with source code.
 * @returns Snippet display text. Not a new stored answer.
 */
export function formatCodeSnippet(text: string): string {
  const fenced = extractFencedCode(text);
  if (fenced !== null) {
    return fenced.code;
  }
  const source = text.replace(/\r\n/g, "\n");
  const starts = [
    source.search(TOOL_PATTERN),
    source.search(DEF_PATTERN),
    source.search(CLASS_PATTERN),
  ].filter((index) => index >= 0);
  const start = starts.length === 0 ? 0 : Math.min(...starts);
  const body = source.slice(start).trim();
  if (body.includes("\n")) {
    let cleaned = body
      .split("\n")
      .map((line) => line.replace(/[ \t]+$/g, ""))
      .join("\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim();
    cleaned = trimTrailingCodeJunk(cleaned);
    // Sparse newlines from salvage (def + body jammed on one line) still need
    // the compact reformatter; true multiline defs keep their line breaks.
    if (looksLikeCompactedCode(cleaned)) {
      return formatCompactCodeSnippet(cleaned.replace(/\n+/g, " "));
    }
    return cleaned;
  }
  return formatCompactCodeSnippet(body);
}

/**
 * Extract the first Markdown fenced code block from a paragraph.
 *
 * @param text - Verified paragraph text.
 * @returns Code and language, or null when no fence is present.
 */
function extractFencedCode(text: string): CodeSnippetModel | null {
  const source = text.replace(/\r\n/g, "\n");
  const whole = source.match(FENCE_WHOLE);
  if (whole) {
    return fenceModel(whole[1] ?? "", whole[2] ?? "");
  }
  const anywhere = source.match(FENCE_ANYWHERE);
  if (anywhere) {
    return fenceModel(anywhere[1] ?? "", anywhere[2] ?? "");
  }
  const openOnly = source.match(FENCE_OPEN_ONLY);
  if (!openOnly) {
    return null;
  }
  const body = (openOnly[2] ?? "")
    .replace(/\n?[ \t]*```[ \t]*\s*$/, "")
    .replace(/\n+$/, "")
    .replace(/^\n+/, "");
  if (!body.trim() || looksLikeProse(body)) {
    return null;
  }
  return fenceModel(openOnly[1] ?? "", body);
}

/**
 * Build a snippet from a fence body.
 *
 * A fence around sentences is not a snippet. The caller renders that
 * body as prose.
 *
 * @param language - Fence info string.
 * @param body - Text between the fences.
 * @returns Snippet, or null when the body is prose.
 */
function fenceModel(language: string, body: string): CodeSnippetModel | null {
  const code = body.replace(/\n+$/, "").replace(/^\n+/, "");
  if (!code.trim() || looksLikeProse(code)) {
    return null;
  }
  return {
    language: normalizeLanguage(language),
    code,
  };
}

/**
 * Return whether fenced text is sentences rather than a listing.
 *
 * @param body - Fence body.
 * @returns True for a long punctuated paragraph with no source statement.
 */
function looksLikeProse(body: string): boolean {
  if (DEF_PATTERN.test(body) || CLASS_PATTERN.test(body) || TOOL_PATTERN.test(body)) {
    return false;
  }
  if (body.split("\n").some((line) => SOURCE_LINE.test(line.trim()))) {
    return false;
  }
  const words = body.trim().split(/\s+/);
  return words.length >= 8 && /[.!?]/.test(body);
}

/**
 * Normalize a fence language tag for the header label.
 *
 * @param raw - Fence info string.
 * @returns Lowercased label, or null when empty.
 */
function normalizeLanguage(raw: string): string | null {
  const trimmed = raw.trim().toLowerCase();
  return trimmed === "" ? null : trimmed;
}

/**
 * Infer a language label for salvaged Python-ish snippets.
 *
 * @param code - Formatted salvage body.
 * @returns `python` when tools/defs look Pythonic, else null.
 */
function inferLanguageFromSalvage(code: string): string | null {
  if (TOOL_PATTERN.test(code) || DEF_PATTERN.test(code) || CLASS_PATTERN.test(code)) {
    return "python";
  }
  return null;
}

/**
 * Drop book section markers and sibling defs that trail a salvage snippet.
 *
 * @param text - Multiline or flat code snippet.
 * @returns Snippet cut before trailing junk when present.
 */
function trimTrailingCodeJunk(text: string): string {
  const section = text.search(/\n?\s*#\s*--\s*\d+/);
  // Only look for a sibling def after the primary ``return`` so the main
  // ``@tool`` / ``def`` header is never mistaken for trailing junk.
  const returnAt = text.search(/\breturn\b/);
  const searchFrom = returnAt >= 0 ? returnAt + "return".length : text.length;
  const siblingRel = text
    .slice(searchFrom)
    .search(/\n\s*(?:@tool\b|(?:async\s+)?def\s+\w+\s*\(|class\s+\w+)/);
  const sibling = siblingRel >= 0 ? searchFrom + siblingRel : -1;
  const cuts = [section, sibling].filter((index) => index > 0);
  if (cuts.length === 0) {
    return text;
  }
  return text.slice(0, Math.min(...cuts)).trim();
}

/**
 * Return whether multiline text still looks like a flattened one-liner.
 *
 * @param text - Candidate snippet after trimming.
 * @returns True when a signature and body share a line.
 */
function looksLikeCompactedCode(text: string): boolean {
  return text.split("\n").some((line) => {
    const hasDef = DEF_PATTERN.test(line);
    const hasToolThenDef = /@tool\b/.test(line) && DEF_PATTERN.test(line);
    const hasDefAndReturn = hasDef && /\breturn\b/.test(line);
    return hasToolThenDef || hasDefAndReturn;
  });
}

/**
 * Reformat a single-line compacted definition into readable lines.
 *
 * @param flatSource - One-line code starting at `@tool` / `def` / `class`.
 * @returns Multiline display text.
 */
function formatCompactCodeSnippet(flatSource: string): string {
  let flat = flatSource.replace(/\s+/g, " ").trim();
  // Drop book section markers that salvage sometimes trails after a tool body.
  flat = flat.replace(/\s+#\s*--\s*\d+[\s\S]*$/, "").trim();
  const lines: string[] = [];
  const decorator = flat.match(/^((?:@\w+\s*)+)/);
  let rest = flat;
  if (decorator) {
    lines.push(...decorator[1].trim().split(/\s+/));
    rest = flat.slice(decorator[1].length).trim();
  }
  const header = rest.match(HEADER_PATTERN);
  if (!header) {
    return [...lines, rest.replace(/\.\s*$/, "")].join("\n");
  }
  lines.push(`${header[1]}:`);
  const body = header[2].trim().replace(/\.\s*$/, "");
  const returnAt = body.search(/\breturn\b/);
  if (returnAt > 0) {
    const docstring = body.slice(0, returnAt).trim();
    let statement = body.slice(returnAt).trim();
    const cut = statement.search(
      /\s+#\s*--|\s+(?:@tool\b|(?:async\s+)?def\s+\w+\s*\(|class\s+\w+)/,
    );
    if (cut > 0) {
      statement = statement.slice(0, cut).trim();
    }
    if (docstring) {
      lines.push(`    ${docstring}`);
    }
    if (statement) {
      lines.push(`    ${statement}`);
    }
  } else if (body) {
    let trimmedBody = body;
    const cut = trimmedBody.search(
      /\s+#\s*--|\s+(?:@tool\b|(?:async\s+)?def\s+\w+\s*\(|class\s+\w+)/,
    );
    if (cut > 0) {
      trimmedBody = trimmedBody.slice(0, cut).trim();
    }
    lines.push(`    ${trimmedBody}`);
  }
  return lines.join("\n");
}
