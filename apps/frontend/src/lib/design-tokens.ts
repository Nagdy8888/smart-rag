/**
 * Canonical design tokens for the production console shell.
 *
 * Values must match the token table in `docs/frontend/STITCH_BRIEF.md`.
 * That brief wins over `DESIGN.md` YAML (lavender canvas, `#004ac6`),
 * prose 10px radius, teal `#0F766E`, and gallery blur. CSS variables in
 * `globals.css` and this module are the implementation source of truth
 * and are tested against the brief hex/px strings.
 *
 * @remarks
 * Do not load Google Fonts or Tailwind from a CDN. Motion must honor
 * `prefers-reduced-motion`. 2026-08-24 Precision Workspace tokens replace
 * the prior Stitch screenshot palette.
 */

/** Page canvas. Not lavender `#faf8ff`. */
export const COLOR_BG = "#F4F6F8";

/** Card and navigation surface. */
export const COLOR_SURFACE = "#FFFFFF";

/** Quiet nested surface. */
export const COLOR_SURFACE_MUTED = "#F8FAFC";

/** Primary body text. WCAG AA on canvas and surface. */
export const COLOR_TEXT = "#182230";

/** Secondary text. AA on white; do not place on `--color-border`. */
export const COLOR_TEXT_MUTED = "#637083";

/** 1px hairline borders. */
export const COLOR_BORDER = "#DDE3EA";

/** Interactive accent and focus color. Not teal `#0F766E`. */
export const COLOR_ACCENT = "#4E5BD5";

/** Text on accent fills. */
export const COLOR_ACCENT_FG = "#FFFFFF";

/** Soft indigo fill for selected navigation. */
export const COLOR_ACCENT_MUTED = "#EEF0FF";

/** Alias of muted indigo. */
export const COLOR_ACCENT_SOFT = "#EEF0FF";

/** Teal evidence/graph signal. Not body text. */
export const COLOR_EVIDENCE = "#0E8584";

/** Destructive / error text on white. */
export const COLOR_DANGER = "#B91C1C";

/** Quota and BM25-degraded warning. Non-alarming. */
export const COLOR_WARNING = "#A16207";

/** Ready / complete status. */
export const COLOR_SUCCESS = "#166534";

/** Keyboard focus ring. 2px solid, 2px offset. */
export const COLOR_FOCUS = "#4E5BD5";

/** Chip and control radius. */
export const RADIUS_SM = "6px";

/** Panel radius. Not 8px Stitch control radius. */
export const RADIUS_MD = "10px";

/** Overlay radius. */
export const RADIUS_LG = "12px";

/** Spacing grid unit. */
export const SPACE = "4px";

/** Resting tonal elevation. No blur. */
export const SHADOW_1 = "0 1px 2px rgb(15 23 42 / 0.08)";

/** Raised tonal elevation for drawers. No blur. */
export const SHADOW_2 = "0 8px 24px rgb(15 23 42 / 0.08)";

/** Self-hosted Inter plus system Arabic fallbacks. No Google Fonts CDN. */
export const FONT_SANS =
  '"Inter", "Segoe UI", "IBM Plex Sans Arabic", "Noto Naskh Arabic", sans-serif';

/** Monospace stack for codes and IDs. */
export const FONT_MONO = 'ui-monospace, "Cascadia Code", monospace';

/** Arabic / diacritic line height. */
export const LINE_HEIGHT_AR = "1.75";

/** English chrome line height. */
export const LINE_HEIGHT_EN = "1.5";

/** Desktop navigation column. */
export const NAV_WIDTH = "232px";

/** Enterprise list and table row minimum height. */
export const ROW_HEIGHT = "48px";

/** Console top bar. */
export const TOPBAR_HEIGHT = "56px";

/**
 * Frozen map of brief CSS custom properties to implementation values.
 *
 * @remarks
 * Tests compare this map to `globals.css`. Adding a token here without
 * updating CSS (or the reverse) is a failing defect.
 */
export const DESIGN_TOKENS = {
  "--color-bg": COLOR_BG,
  "--color-surface": COLOR_SURFACE,
  "--color-surface-muted": COLOR_SURFACE_MUTED,
  "--color-text": COLOR_TEXT,
  "--color-text-muted": COLOR_TEXT_MUTED,
  "--color-border": COLOR_BORDER,
  "--color-accent": COLOR_ACCENT,
  "--color-accent-fg": COLOR_ACCENT_FG,
  "--color-accent-muted": COLOR_ACCENT_MUTED,
  "--color-accent-soft": COLOR_ACCENT_SOFT,
  "--color-evidence": COLOR_EVIDENCE,
  "--color-danger": COLOR_DANGER,
  "--color-warning": COLOR_WARNING,
  "--color-success": COLOR_SUCCESS,
  "--color-focus": COLOR_FOCUS,
  "--radius-sm": RADIUS_SM,
  "--radius-md": RADIUS_MD,
  "--radius-lg": RADIUS_LG,
  "--space": SPACE,
  "--shadow-1": SHADOW_1,
  "--shadow-2": SHADOW_2,
  "--font-sans": FONT_SANS,
  "--font-mono": FONT_MONO,
  "--line-height-ar": LINE_HEIGHT_AR,
  "--line-height-en": LINE_HEIGHT_EN,
  "--nav-width": NAV_WIDTH,
  "--row-height": ROW_HEIGHT,
  "--topbar-height": TOPBAR_HEIGHT,
} as const;

/** CSS custom property names owned by the brief plus shell metrics. */
export type DesignTokenName = keyof typeof DESIGN_TOKENS;
