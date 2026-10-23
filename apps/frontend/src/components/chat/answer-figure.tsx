/**
 * Authorized figure image. The model cannot supply the URL.
 */

"use client";

import { useEffect, useRef, useState } from "react";
import { apiUrl } from "../../lib/api/http";
import { useOptionalSession } from "../../lib/auth/session-provider";
import { Sheet } from "../ui/sheet";
import { renderAnswerInline } from "../../lib/answer-prose";
import styles from "./chat-transcript.module.css";

const FIGURE_MARK = /\[\[figure:([A-Za-z0-9-]{1,64})\]\]/;

/** All explicit assets in a paragraph, including UUIDs; never model URLs. */
export function figureIdsInText(text: string): string[] {
  return [...new Set([...text.matchAll(new RegExp(FIGURE_MARK.source, "g"))].map((m) => m[1]))];
}

export function stripFigureMarks(text: string): string {
  return text.replace(new RegExp(FIGURE_MARK.source, "g"), "").trim();
}

/**
 * Split a paragraph into prose and an optional figure id.
 *
 * @param text - Paragraph that may end with a figure mark.
 * @returns Prose without the mark, and the figure id when present.
 */
export function splitFigureMark(text: string): {
  prose: string;
  figureId: string | null;
} {
  const match = FIGURE_MARK.exec(text);
  if (match === null || match[1] === undefined) {
    return { prose: text, figureId: null };
  }
  return {
    prose: text.replace(FIGURE_MARK, "").trim(),
    figureId: match[1],
  };
}

/**
 * Load one figure through the authorized API and show it as an image.
 *
 * The bytes stay on a blob URL. CSP must allow `blob:` in `img-src`; a
 * remote image host is never accepted.
 *
 * @param props - Figure id and caption text. Caption is rendered as text.
 */
export function AnswerFigure({
  figureId,
  caption,
}: {
  figureId: string;
  caption: string;
}) {
  const session = useOptionalSession();
  const token = session?.accessToken ?? null;
  return (
    <FigureAsset
      key={JSON.stringify([figureId, token])}
      figureId={figureId}
      token={token}
      caption={caption}
    />
  );
}

/** Split existing figure text into its introduction, printed caption, and description. */
export function figureTextParts(text: string) {
  const lines = text.split("\n");
  const captionIndex = lines.findIndex((line) =>
    /^\s*(?:Figure|Fig\.)\s+\d+[.\d\u2013-]*[.:]?\s+/i.test(line),
  );
  if (captionIndex < 0)
    return { introduction: "", caption: text, description: "" };
  return {
    introduction: lines.slice(0, captionIndex).join("\n").trim(),
    caption: lines[captionIndex].trim(),
    description: lines
      .slice(captionIndex + 1)
      .join("\n")
      .trim(),
  };
}

/** Own one authenticated image request and its accessible enlargement sheet. */
function FigureAsset({
  figureId,
  token,
  caption,
}: {
  figureId: string;
  token: string | null;
  caption: string;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const expandTrigger = useRef<HTMLButtonElement>(null);
  const parts = figureTextParts(caption);
  const alt = parts.caption || "Document figure";

  useEffect(() => {
    if (token === null) return;
    const controller = new AbortController();
    let active = true;
    let objectUrl = "";
    void fetch(apiUrl(`/figures/${figureId}`), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("figure_unavailable");
        const blob = await response.blob();
        if (blob.type !== "image/png" && blob.type !== "")
          throw new Error("figure_unavailable");
        if (!active) return;
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (active) setFailed(true);
      });
    return () => {
      active = false;
      controller.abort();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [figureId, token]);

  return (
    <>
      {parts.introduction ? (
        <p className={styles.answerProse} dir="auto">
          {renderAnswerInline(parts.introduction, styles.answerInlineCode)}
        </p>
      ) : null}
      <figure className={styles.answerFigure} data-testid="answer-figure">
        {src ? (
          <button
            ref={expandTrigger}
            type="button"
            className={styles.figureExpand}
            aria-label="Enlarge diagram"
            onClick={() => setExpanded(true)}
          >
            <img className={styles.answerFigureImage} src={src} alt={alt} />
            <span className={styles.figureExpandHint}>Enlarge diagram</span>
          </button>
        ) : (
          <p className={styles.muted} role="status">
            {failed || token === null
              ? "Diagram preview is unavailable."
              : "Loading diagram…"}
          </p>
        )}
        {parts.caption ? (
          <figcaption className={styles.answerFigureCaption} dir="auto">
            {renderAnswerInline(parts.caption, styles.answerInlineCode)}
          </figcaption>
        ) : null}
        {parts.description ? (
          <details className={styles.figureDescription}>
            <summary>Diagram description</summary>
            <p dir="auto">
              {renderAnswerInline(parts.description, styles.answerInlineCode)}
            </p>
          </details>
        ) : null}
      </figure>
      {expanded && src ? (
        <Sheet
          title="Diagram"
          panelClassName={styles.figureReader}
          returnFocusRef={expandTrigger}
          onClose={() => setExpanded(false)}
        >
          <img className={styles.figureReaderImage} src={src} alt={alt} />
          <p dir="auto">
            {renderAnswerInline(parts.caption, styles.answerInlineCode)}
          </p>
        </Sheet>
      ) : null}
    </>
  );
}
