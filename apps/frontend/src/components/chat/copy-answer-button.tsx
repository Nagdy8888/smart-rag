"use client";

import { useEffect, useState } from "react";
import { displayText } from "../../lib/safe-text";
import { Button } from "../ui/button";

/** Copy the complete answer, retaining code and removing internal figure markers. */
export function CopyAnswerButton({ text }: { text: string }) {
  const [status, setStatus] = useState<"idle" | "copied" | "failed">("idle");
  useEffect(() => {
    if (status === "idle") return;
    const timer = window.setTimeout(() => setStatus("idle"), 2000);
    return () => window.clearTimeout(timer);
  }, [status]);
  return (
    <Button
      type="button"
      variant="ghost"
      size="compact"
      aria-label="Copy answer"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(
            displayText(text)
              .replace(/\[\[figure:[A-Za-z0-9]{1,64}\]\]/g, "")
              .trim(),
          );
          setStatus("copied");
        } catch {
          setStatus("failed");
        }
      }}
    >
      <span role="status">
        {status === "copied"
          ? "Copied"
          : status === "failed"
            ? "Copy failed"
            : "Copy answer"}
      </span>
    </Button>
  );
}
