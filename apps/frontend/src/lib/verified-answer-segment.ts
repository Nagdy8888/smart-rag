/**
 * Unicode-safe grapheme segmentation for verified-answer presentation.
 */

/**
 * Split verified text into grapheme clusters.
 *
 * Uses `Intl.Segmenter` with locale `und` and `granularity: "grapheme"`.
 * If the constructor is missing or throws, the original string is returned
 * as a single segment. Callers must never slice UTF-16 code units.
 *
 * @param text - Authoritative verified answer text.
 * @returns Grapheme segments whose join equals `text`.
 */
export function segmentVerifiedText(text: string): readonly string[] {
  if (text === "") {
    return [];
  }
  try {
    if (typeof Intl === "undefined" || typeof Intl.Segmenter !== "function") {
      return [text];
    }
    const segmenter = new Intl.Segmenter("und", { granularity: "grapheme" });
    return Array.from(segmenter.segment(text), (item) => item.segment);
  } catch {
    return [text];
  }
}
