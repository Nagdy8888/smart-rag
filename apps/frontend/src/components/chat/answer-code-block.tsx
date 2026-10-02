/**
 * Chat-product code block chrome for verified answer snippets.
 */

"use client";

import { useEffect, useState, type ReactNode } from "react";
import { UserText } from "../ui/user-text";
import { Button } from "../ui/button";
import styles from "./chat-transcript.module.css";

export type AnswerCodeBlockProps = {
  /** Formatted source body. */
  code: string;
  /** Optional language label for the header. */
  language?: string | null;
};

/**
 * Render a framed code block with language label and Copy control.
 *
 * @param props - Code body and optional language.
 * @returns Code chrome. Content stays React text nodes.
 * @remarks
 * Side effects: clipboard write on Copy. Missing clipboard shows failure.
 */
export function AnswerCodeBlock({
  code,
  language = null,
}: AnswerCodeBlockProps): ReactNode {
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  useEffect(() => {
    if (state === "idle") {
      return;
    }
    const timer = window.setTimeout(() => {
      setState("idle");
    }, 2000);
    return () => {
      window.clearTimeout(timer);
    };
  }, [state]);

  const label = language && language.trim() !== "" ? language.trim() : "code";

  return (
    <div className={styles.codeBlock} data-testid="answer-code-snippet">
      <div className={styles.codeBlockHeader}>
        <span className={styles.codeBlockLang}>{label}</span>
        <Button
          type="button"
          variant="ghost"
          size="compact"
          aria-label={`Copy ${label} snippet`}
          onClick={() => {
            void (async () => {
              if (navigator.clipboard?.writeText === undefined) {
                setState("failed");
                return;
              }
              try {
                await navigator.clipboard.writeText(code);
                setState("copied");
              } catch {
                setState("failed");
              }
            })();
          }}
        >
          {state === "copied" ? "Copied" : state === "failed" ? "Copy failed" : "Copy"}
        </Button>
      </div>
      <pre className={styles.codeBlockBody}>
        <code dir="ltr">
          <UserText value={code} />
        </code>
      </pre>
    </div>
  );
}
