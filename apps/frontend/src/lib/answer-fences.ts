/** Split complete mixed prose/code content without discarding either side. */
export function splitAnswerFences(text: string): string[] | null {
  const fences = [...text.matchAll(/```[^\n]*\n[\s\S]*?\n[ \t]*```/g)];
  if (fences.length === 0) return null;
  const parts: string[] = [];
  let cursor = 0;
  for (const fence of fences) {
    const at = fence.index;
    const prefix = text.slice(cursor, at);
    if (prefix.trim()) parts.push(prefix);
    parts.push(fence[0]);
    cursor = at + fence[0].length;
  }
  const suffix = text.slice(cursor);
  if (suffix.trim()) parts.push(suffix);
  // A whole-paragraph fence stays on the normal code/table/prose path.
  return parts.length > 1 ? parts : null;
}
