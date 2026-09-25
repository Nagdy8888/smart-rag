/**
 * Display-only formatting for verified answer paragraphs that contain source code.
 *
 * Stored answer text is unchanged. Rendering stays React text nodes.
 */

const DEF_PATTERN = /\b(?:async\s+)?def\s+\w+\s*\(/;
const CLASS_PATTERN = /\bclass\s+\w+/;
const HEADER_PATTERN =
  /^((?:async\s+)?(?:def|class)\s+\w+\s*\([^)]*\)[^:]*):\s*([\s\S]*)$/;

/**
 * Return whether a verified paragraph contains a function or class to show as code.
 *
 * @param text - One verified paragraph.
 * @returns True when a definition is present.
 */
export function isCodeSnippet(text: string): boolean {
  return DEF_PATTERN.test(text) || CLASS_PATTERN.test(text);
}

/**
 * Return only the function or class, with the docstring and return on their own lines.
 *
 * The split follows the signature colon after the parameter list, so type
 * hints inside the parentheses stay on the `def` line. Quote characters in
 * the docstring do not matter.
 *
 * @param text - Paragraph that mixes a sentence with source code.
 * @returns Snippet display text. Not a new stored answer.
 */
export function formatCodeSnippet(text: string): string {
  const source = text.replace(/\r\n/g, "\n");
  const starts = [source.search(/@\w+/), source.search(DEF_PATTERN), source.search(CLASS_PATTERN)].filter(
    (index) => index >= 0,
  );
  const start = starts.length === 0 ? 0 : Math.min(...starts);
  const flat = source.slice(start).replace(/\s+/g, " ").trim();
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
    const statement = body.slice(returnAt).trim();
    if (docstring) {
      lines.push(`    ${docstring}`);
    }
    if (statement) {
      lines.push(`    ${statement}`);
    }
  } else if (body) {
    lines.push(`    ${body}`);
  }
  return lines.join("\n");
}
