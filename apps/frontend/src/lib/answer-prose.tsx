/**
 * Safe React-only markdown-lite for verified answer prose paragraphs.
 *
 * Emits element trees with text children. Never HTML strings or
 * dangerouslySetInnerHTML. Hostile markup stays inert text.
 */

import { createElement, type ReactNode } from "react";
import { displayText } from "./safe-text";

const BULLET = /^\s*[-*]\s+(.+)$/;
const ORDERED = /^\s*(\d+)\.\s+(.+)$/;
const BOLD = /\*\*([^*]+)\*\*/g;
const INLINE_CODE = /`([^`]+)`/g;

/**
 * Render one verified prose paragraph with lists, bold, and inline code.
 *
 * @param text - Decoded paragraph text.
 * @param className - CSS module class for paragraph blocks.
 * @param listClassName - CSS module class for list blocks.
 * @param inlineCodeClassName - CSS module class for inline code.
 * @returns React nodes. XSS payloads remain text.
 */
export function renderAnswerProse(
  text: string,
  className: string,
  listClassName: string,
  inlineCodeClassName: string,
): ReactNode {
  const source = text.replace(/\r\n/g, "\n");
  const blocks = splitProseBlocks(source);
  if (blocks.length === 0) {
    return null;
  }
  return createElement(
    "div",
    { "data-testid": "answer-prose" },
    ...blocks.map((block, index) => {
      if (block.kind === "ul" || block.kind === "ol") {
        return createElement(
          block.kind,
          {
            key: `list-${String(index)}`,
            className: listClassName,
            dir: "auto",
          },
          ...block.items.map((item, itemIndex) =>
            createElement(
              "li",
              { key: `li-${String(index)}-${String(itemIndex)}` },
              ...renderInline(item, inlineCodeClassName),
            ),
          ),
        );
      }
      if (block.kind !== "p") {
        return null;
      }
      return createElement(
        "p",
        {
          key: `p-${String(index)}`,
          className,
          dir: "auto",
        },
        ...renderInline(block.text, inlineCodeClassName),
      );
    }),
  );
}

type ProseBlock =
  | { kind: "p"; text: string }
  | { kind: "ul" | "ol"; items: string[] };

/**
 * Split paragraph text into prose and list blocks on blank lines / list runs.
 *
 * @param source - Normalized newline text.
 * @returns Ordered blocks for rendering.
 */
function splitProseBlocks(source: string): ProseBlock[] {
  const lines = source.split("\n");
  const blocks: ProseBlock[] = [];
  let paragraphLines: string[] = [];
  let listKind: "ul" | "ol" | null = null;
  let listItems: string[] = [];

  const flushParagraph = (): void => {
    const text = paragraphLines.join("\n").trim();
    paragraphLines = [];
    if (text) {
      blocks.push({ kind: "p", text });
    }
  };

  const flushList = (): void => {
    if (listKind !== null && listItems.length > 0) {
      blocks.push({ kind: listKind, items: listItems });
    }
    listKind = null;
    listItems = [];
  };

  for (const line of lines) {
    const bullet = line.match(BULLET);
    const ordered = line.match(ORDERED);
    if (bullet) {
      flushParagraph();
      if (listKind !== null && listKind !== "ul") {
        flushList();
      }
      listKind = "ul";
      listItems.push(bullet[1] ?? "");
      continue;
    }
    if (ordered) {
      flushParagraph();
      if (listKind !== null && listKind !== "ol") {
        flushList();
      }
      listKind = "ol";
      listItems.push(ordered[2] ?? "");
      continue;
    }
    if (line.trim() === "") {
      flushList();
      flushParagraph();
      continue;
    }
    flushList();
    paragraphLines.push(line);
  }
  flushList();
  flushParagraph();
  return blocks;
}

/**
 * Render inline bold and backtick code as React nodes.
 *
 * @param text - One line or paragraph body.
 * @param inlineCodeClassName - Class for inline code.
 * @returns Mixed text and element children.
 */
function renderInline(text: string, inlineCodeClassName: string): ReactNode[] {
  const safe = displayText(text);
  const parts: ReactNode[] = [];
  // Split on inline code first so backticks inside bold stay literal.
  const codeSplit = splitByPattern(safe, INLINE_CODE);
  let key = 0;
  for (const piece of codeSplit) {
    if (piece.type === "match") {
      parts.push(
        createElement(
          "code",
          { key: `c-${String(key)}`, className: inlineCodeClassName },
          piece.capture,
        ),
      );
      key += 1;
      continue;
    }
    const boldSplit = splitByPattern(piece.value, BOLD);
    for (const boldPiece of boldSplit) {
      if (boldPiece.type === "match") {
        parts.push(
          createElement("strong", { key: `b-${String(key)}` }, boldPiece.capture),
        );
        key += 1;
      } else if (boldPiece.value) {
        parts.push(boldPiece.value);
      }
    }
  }
  return parts.length > 0 ? parts : [safe];
}

type SplitPiece =
  | { type: "text"; value: string }
  | { type: "match"; capture: string };

/**
 * Split a string by a global capturing regex into text and match pieces.
 *
 * @param text - Source string.
 * @param pattern - Global regex with one capture group.
 * @returns Ordered pieces covering the full string.
 */
function splitByPattern(text: string, pattern: RegExp): SplitPiece[] {
  const pieces: SplitPiece[] = [];
  const flags = pattern.flags.includes("g") ? pattern.flags : `${pattern.flags}g`;
  const re = new RegExp(pattern.source, flags);
  let last = 0;
  let match = re.exec(text);
  while (match) {
    if (match.index > last) {
      pieces.push({ type: "text", value: text.slice(last, match.index) });
    }
    pieces.push({ type: "match", capture: match[1] ?? "" });
    last = match.index + match[0].length;
    match = re.exec(text);
  }
  if (last < text.length) {
    pieces.push({ type: "text", value: text.slice(last) });
  }
  return pieces;
}
