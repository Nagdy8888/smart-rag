/**
 * Safe React-only markdown-lite for verified answer prose paragraphs.
 *
 * Emits element trees with text children. Hostile markup stays inert text.
 */

import { createElement, type ReactNode } from "react";
import { displayText, isSafeHttpUrl } from "./safe-text";

const BULLET = /^\s*[-*]\s+(.+)$/;
const ORDERED = /^\s*(\d+)\.\s+(.+)$/;
const BOLD = /\*\*([^*]+)\*\*/g;
const INLINE_CODE = /`([^`]+)`/g;
/** Markdown link or a bare http(s) address. Group 1 is the label, group 2 the URL. */
const LINK_OR_URL =
  /\[([^\]\n]+)\]\(([^)\s]+)\)|https?:\/\/[^\s<>"']+/g;

/**
 * Render one verified prose paragraph with lists, bold, inline code, and links.
 *
 * Only http and https addresses become anchors. Other schemes stay text.
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
 * Render inline bold, backtick code, and clickable http(s) links.
 *
 * @param text - One line, cell, or paragraph body. HTML is not parsed.
 * @param inlineCodeClassName - Class for inline code.
 * @returns Mixed text and element children.
 */
export function renderAnswerInline(
  text: string,
  inlineCodeClassName: string,
): ReactNode[] {
  const safe = displayText(text);
  const parts: ReactNode[] = [];
  const codeSplit = splitByPattern(safe, INLINE_CODE);
  let key = 0;
  const nextKey = (): string => {
    key += 1;
    return String(key);
  };
  for (const piece of codeSplit) {
    if (piece.type === "match") {
      parts.push(
        createElement(
          "code",
          { key: `c-${nextKey()}`, className: inlineCodeClassName },
          piece.capture,
        ),
      );
      continue;
    }
    const boldSplit = splitByPattern(piece.value, BOLD);
    for (const boldPiece of boldSplit) {
      if (boldPiece.type === "match") {
        parts.push(
          createElement(
            "strong",
            { key: `b-${nextKey()}` },
            ...appendLinks(boldPiece.capture, nextKey),
          ),
        );
      } else if (boldPiece.value) {
        parts.push(...appendLinks(boldPiece.value, nextKey));
      }
    }
  }
  return parts.length > 0 ? parts : [safe];
}

/**
 * Render inline bold and backtick code as React nodes.
 *
 * @param text - One line or paragraph body.
 * @param inlineCodeClassName - Class for inline code.
 * @returns Mixed text and element children.
 */
function renderInline(text: string, inlineCodeClassName: string): ReactNode[] {
  return renderAnswerInline(text, inlineCodeClassName);
}

/**
 * Turn markdown links and bare http(s) addresses into anchors.
 *
 * @param text - Text that is not inside inline code.
 * @param nextKey - Key factory for sibling nodes.
 * @returns Text nodes and anchors. Unsafe URLs stay text.
 */
function appendLinks(text: string, nextKey: () => string): ReactNode[] {
  const parts: ReactNode[] = [];
  const pattern = new RegExp(LINK_OR_URL.source, "g");
  let last = 0;
  let match = pattern.exec(text);
  while (match) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const label = match[1];
    const markdownUrl = match[2];
    if (label !== undefined && markdownUrl !== undefined) {
      if (isSafeHttpUrl(markdownUrl)) {
        parts.push(answerLink(markdownUrl, label, nextKey()));
      } else {
        parts.push(match[0]);
      }
    } else {
      const trimmed = trimUrlTail(match[0]);
      if (isSafeHttpUrl(trimmed.href)) {
        parts.push(answerLink(trimmed.href, trimmed.href, nextKey()));
        if (trimmed.tail) {
          parts.push(trimmed.tail);
        }
      } else {
        parts.push(match[0]);
      }
    }
    last = match.index + match[0].length;
    match = pattern.exec(text);
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts.length > 0 ? parts : [text];
}

/**
 * Build one external answer link. The label is a text child, never HTML.
 *
 * @param href - http or https URL already checked with `isSafeHttpUrl`.
 * @param label - Visible text.
 * @param key - React key.
 * @returns Anchor that opens in a new tab.
 */
function answerLink(href: string, label: string, key: string): ReactNode {
  return createElement(
    "a",
    {
      key: `a-${key}`,
      href,
      target: "_blank",
      rel: "noopener noreferrer",
    },
    label,
  );
}

/**
 * Drop sentence punctuation that stuck to a bare URL.
 *
 * @param raw - Matched address, possibly with a trailing period.
 * @returns Href and the punctuation that should stay outside the link.
 */
function trimUrlTail(raw: string): { href: string; tail: string } {
  let href = raw;
  let tail = "";
  while (href.length > 0 && /[.,;:!?)]$/.test(href)) {
    const last = href.slice(-1);
    if (last === ")") {
      const opens = href.split("(").length - 1;
      const closes = href.split(")").length - 1;
      if (opens >= closes) {
        break;
      }
    }
    tail = last + tail;
    href = href.slice(0, -1);
  }
  return { href, tail };
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
