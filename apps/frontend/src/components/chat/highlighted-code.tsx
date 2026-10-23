/** Syntax tokens stay React text nodes; source code is never interpreted as HTML. */
import { common, createLowlight } from "lowlight";
import { useMemo, type ReactNode } from "react";

const highlighter = createLowlight(common);
type Token = ReturnType<typeof highlighter.highlight>["children"][number];

function renderToken(token: Token, key: number): ReactNode {
  if (token.type === "text") return token.value;
  if (token.type !== "element") return null;
  const classes = token.properties.className;
  return (
    <span key={key} className={Array.isArray(classes) ? classes.join(" ") : undefined}>
      {token.children.map(renderToken)}
    </span>
  );
}

/** Unknown languages and oversized snippets retain their exact plain text. */
export function HighlightedCode({ code, language }: { code: string; language: string | null }) {
  return useMemo(() => {
    const name = language?.trim().toLowerCase();
    if (!name || !highlighter.registered(name) || code.length > 32_768) return code;
    try {
      return highlighter.highlight(name, code).children.map(renderToken);
    } catch {
      return code;
    }
  }, [code, language]);
}
