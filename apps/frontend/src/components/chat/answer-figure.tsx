/**
 * Authorized figure image. The model cannot supply the URL.
 */

"use client";

import { useEffect, useState } from "react";
import { apiUrl } from "../../lib/api/http";
import { useOptionalSession } from "../../lib/auth/session-provider";
import { UserText } from "../ui/user-text";
import styles from "./chat-transcript.module.css";

const FIGURE_MARK = /\[\[figure:([A-Za-z0-9]{1,64})\]\]/;

/**
 * Split a paragraph into prose and an optional figure id.
 *
 * @param text - Paragraph that may end with a figure mark.
 * @returns Prose without the mark, and the figure id when present.
 */
export function splitFigureMark(text: string): { prose: string; figureId: string | null } {
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
  const [src, setSrc] = useState<string | null>(null);

  useEffect(() => {
    if (token === null) {
      return;
    }
    const controller = new AbortController();
    let active = true;
    let objectUrl = "";
    void fetch(apiUrl(`/figures/${figureId}`), {
      headers: { Authorization: `Bearer ${token}` },
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!active || !response.ok) {
          return;
        }
        const blob = await response.blob();
        if (!active || (blob.type !== "image/png" && blob.type !== "")) {
          return;
        }
        objectUrl = URL.createObjectURL(blob);
        setSrc(objectUrl);
      })
      .catch(() => {
        if (active) {
          setSrc(null);
        }
      });
    return () => {
      active = false;
      controller.abort();
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [figureId, token]);

  return (
    <figure className={styles.answerFigure} data-testid="answer-figure">
      {src ? (
        <img
          className={styles.answerFigureImage}
          src={src}
          alt={caption || "Document figure"}
        />
      ) : null}
      {caption ? (
        <figcaption className={styles.answerFigureCaption}>
          <UserText value={caption} />
        </figcaption>
      ) : null}
    </figure>
  );
}
