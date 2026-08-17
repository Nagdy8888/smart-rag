/**
 * WCAG 2 contrast helpers for design-token unit tests.
 *
 * Ratios use relative luminance (sRGB). These helpers do not fetch and
 * do not claim runtime theme switching.
 */

const HEX = /^#([0-9a-fA-F]{6})$/;

/**
 * Parse a six-digit hex color into 0–255 sRGB channels.
 *
 * @param hex - `#RRGGBB`.
 * @returns Channels, or null when the string is not a six-digit hex.
 */
export function parseHexColor(
  hex: string,
): { r: number; g: number; b: number } | null {
  const match = HEX.exec(hex.trim());
  if (match === null || match[1] === undefined) {
    return null;
  }
  const value = match[1];
  return {
    r: Number.parseInt(value.slice(0, 2), 16),
    g: Number.parseInt(value.slice(2, 4), 16),
    b: Number.parseInt(value.slice(4, 6), 16),
  };
}

/**
 * Linearize one sRGB channel for relative luminance.
 *
 * @param channel - 0–255.
 * @returns 0–1 linearized component.
 */
function linearizeChannel(channel: number): number {
  const srgb = channel / 255;
  if (srgb <= 0.04045) {
    return srgb / 12.92;
  }
  return ((srgb + 0.055) / 1.055) ** 2.4;
}

/**
 * Return WCAG relative luminance of a hex color.
 *
 * @param hex - `#RRGGBB`.
 * @returns 0–1 luminance. Invalid hex returns 0.
 */
export function relativeLuminance(hex: string): number {
  const rgb = parseHexColor(hex);
  if (rgb === null) {
    return 0;
  }
  const r = linearizeChannel(rgb.r);
  const g = linearizeChannel(rgb.g);
  const b = linearizeChannel(rgb.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/**
 * Return the WCAG contrast ratio between two hex colors.
 *
 * @param foreground - Text `#RRGGBB`.
 * @param background - Surface `#RRGGBB`.
 * @returns Ratio ≥ 1. Invalid hex yields 1.
 */
export function contrastRatio(foreground: string, background: string): number {
  const left = relativeLuminance(foreground);
  const right = relativeLuminance(background);
  const lighter = Math.max(left, right);
  const darker = Math.min(left, right);
  return (lighter + 0.05) / (darker + 0.05);
}

/** WCAG AA minimum contrast for normal body text. */
export const WCAG_AA_NORMAL_TEXT = 4.5;
