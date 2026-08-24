/**
 * Canonical design tokens for the production console.
 *
 * Values must match the Phase 8 visual contract and `globals.css` `:root`.
 * CSS variables plus this module are the implementation source of truth.
 *
 * @remarks
 * Do not load Google Fonts or Tailwind from a CDN. Motion honors
 * `prefers-reduced-motion`. P08-13 tokens replace the prior incomplete palette.
 */

/** Page canvas. Not lavender `#faf8ff`. */
export const COLOR_BG = "#F4F6F8";

/** Card, drawer, topbar, nav, and input surface. */
export const COLOR_SURFACE = "#FFFFFF";

/** Secondary panels, table headers, code blocks. */
export const COLOR_SURFACE_MUTED = "#F8FAFC";

/** Neutral hover fill. */
export const COLOR_SURFACE_HOVER = "#F1F4F8";

/** Selected navigation or list row. */
export const COLOR_SURFACE_SELECTED = "#EEF0FF";

/** Primary body text. Never pure black. */
export const COLOR_TEXT = "#182230";

/** Secondary body text. */
export const COLOR_TEXT_SECONDARY = "#475467";

/** Metadata and helper text. */
export const COLOR_TEXT_MUTED = "#637083";

/** Disabled text only. */
export const COLOR_TEXT_DISABLED = "#8A94A3";

/** Default borders. */
export const COLOR_BORDER = "#DDE3EA";

/** Emphasized separators and input hover. */
export const COLOR_BORDER_STRONG = "#C7D0DB";

/** Primary action and active navigation. */
export const COLOR_ACCENT = "#4E5BD5";

/** Primary hover. */
export const COLOR_ACCENT_HOVER = "#414CC4";

/** Primary pressed. */
export const COLOR_ACCENT_PRESSED = "#343DA8";

/** Text on primary fills. */
export const COLOR_ACCENT_FG = "#FFFFFF";

/** Selected / muted accent fill. */
export const COLOR_ACCENT_MUTED = "#EEF0FF";

/** Alias of muted accent for existing callers. */
export const COLOR_ACCENT_SOFT = "#EEF0FF";

/** Selected outline. */
export const COLOR_ACCENT_BORDER = "#C9CDF8";

/** Citations and provenance only. */
export const COLOR_EVIDENCE = "#0E8584";

/** Evidence hover. */
export const COLOR_EVIDENCE_HOVER = "#0A6F6E";

/** Evidence muted fill. */
export const COLOR_EVIDENCE_MUTED = "#ECFDFC";

/** Success text. */
export const COLOR_SUCCESS = "#166534";

/** Success fill. */
export const COLOR_SUCCESS_BG = "#F0FDF4";

/** Success border. */
export const COLOR_SUCCESS_BORDER = "#BBF7D0";

/** Warning text. */
export const COLOR_WARNING = "#A16207";

/** Warning fill. */
export const COLOR_WARNING_BG = "#FFFBEB";

/** Warning border. */
export const COLOR_WARNING_BORDER = "#FDE68A";

/** Danger text and fills. */
export const COLOR_DANGER = "#B91C1C";

/** Danger hover. */
export const COLOR_DANGER_HOVER = "#991B1B";

/** Danger fill. */
export const COLOR_DANGER_BG = "#FEF2F2";

/** Danger border. */
export const COLOR_DANGER_BORDER = "#FECACA";

/** Info text. */
export const COLOR_INFO = "#1D4ED8";

/** Info fill. */
export const COLOR_INFO_BG = "#EFF6FF";

/** Info border. */
export const COLOR_INFO_BORDER = "#BFDBFE";

/** Keyboard focus ring. */
export const COLOR_FOCUS = "#4E5BD5";

/** Modal overlay. No blur. */
export const COLOR_OVERLAY = "rgb(15 23 42 / 0.42)";

/** Control radius (buttons, inputs). */
export const RADIUS_SM = "8px";

/** Card, panel, dialog radius. */
export const RADIUS_MD = "12px";

/** Overlay radius (same as cards). */
export const RADIUS_LG = "12px";

/** Status pill radius. */
export const RADIUS_PILL = "999px";

/** Spacing grid unit. */
export const SPACE = "4px";

/** Resting elevation. */
export const SHADOW_1 = "0 1px 2px rgb(15 23 42 / 0.08)";

/** Dialog and drawer elevation. */
export const SHADOW_2 = "0 8px 24px rgb(15 23 42 / 0.10)";

/** Self-hosted Inter plus system Arabic fallbacks. */
export const FONT_SANS =
  '"Inter", "Segoe UI", "IBM Plex Sans Arabic", "Noto Naskh Arabic", sans-serif';

/** Monospace stack for codes and IDs. */
export const FONT_MONO =
  'ui-monospace, "Cascadia Code", "SFMono-Regular", Consolas, monospace';

/** Arabic / mixed line height. */
export const LINE_HEIGHT_AR = "1.75";

/** English chrome line height. */
export const LINE_HEIGHT_EN = "1.5";

/** Desktop navigation column. */
export const NAV_WIDTH = "232px";

/** Collapsed navigation column. */
export const NAV_WIDTH_COLLAPSED = "72px";

/** Enterprise table/list row minimum. */
export const ROW_HEIGHT = "48px";

/** Console top bar. */
export const TOPBAR_HEIGHT = "56px";

/** Standard control height. */
export const CONTROL_HEIGHT = "40px";

/** Compact control height. */
export const CONTROL_HEIGHT_COMPACT = "32px";

/** Large / auth primary control height. */
export const CONTROL_HEIGHT_LG = "44px";

/** Default icon button size. */
export const ICON_BUTTON_SIZE = "36px";

/** Page title size. */
export const TEXT_PAGE_TITLE_SIZE = "24px";

/** Page title line height. */
export const TEXT_PAGE_TITLE_HEIGHT = "32px";

/** Body size. */
export const TEXT_BODY_SIZE = "14px";

/** Body line height. */
export const TEXT_BODY_HEIGHT = "20px";

/** Label size. */
export const TEXT_LABEL_SIZE = "13px";

/** Label line height. */
export const TEXT_LABEL_HEIGHT = "18px";

/** Hover/focus transition. */
export const MOTION_FAST = "120ms";

/** Drawer/dialog transition. */
export const MOTION_PANEL = "160ms";

/**
 * Frozen map of CSS custom properties to implementation values.
 *
 * @remarks
 * Tests compare this map to `globals.css`. Adding a token here without
 * updating CSS (or the reverse) is a failing defect.
 */
export const DESIGN_TOKENS = {
  "--color-bg": COLOR_BG,
  "--color-surface": COLOR_SURFACE,
  "--color-surface-muted": COLOR_SURFACE_MUTED,
  "--color-surface-hover": COLOR_SURFACE_HOVER,
  "--color-surface-selected": COLOR_SURFACE_SELECTED,
  "--color-text": COLOR_TEXT,
  "--color-text-secondary": COLOR_TEXT_SECONDARY,
  "--color-text-muted": COLOR_TEXT_MUTED,
  "--color-text-disabled": COLOR_TEXT_DISABLED,
  "--color-border": COLOR_BORDER,
  "--color-border-strong": COLOR_BORDER_STRONG,
  "--color-accent": COLOR_ACCENT,
  "--color-accent-hover": COLOR_ACCENT_HOVER,
  "--color-accent-pressed": COLOR_ACCENT_PRESSED,
  "--color-accent-fg": COLOR_ACCENT_FG,
  "--color-accent-muted": COLOR_ACCENT_MUTED,
  "--color-accent-soft": COLOR_ACCENT_SOFT,
  "--color-accent-border": COLOR_ACCENT_BORDER,
  "--color-evidence": COLOR_EVIDENCE,
  "--color-evidence-hover": COLOR_EVIDENCE_HOVER,
  "--color-evidence-muted": COLOR_EVIDENCE_MUTED,
  "--color-success": COLOR_SUCCESS,
  "--color-success-bg": COLOR_SUCCESS_BG,
  "--color-success-border": COLOR_SUCCESS_BORDER,
  "--color-warning": COLOR_WARNING,
  "--color-warning-bg": COLOR_WARNING_BG,
  "--color-warning-border": COLOR_WARNING_BORDER,
  "--color-danger": COLOR_DANGER,
  "--color-danger-hover": COLOR_DANGER_HOVER,
  "--color-danger-bg": COLOR_DANGER_BG,
  "--color-danger-border": COLOR_DANGER_BORDER,
  "--color-info": COLOR_INFO,
  "--color-info-bg": COLOR_INFO_BG,
  "--color-info-border": COLOR_INFO_BORDER,
  "--color-focus": COLOR_FOCUS,
  "--color-overlay": COLOR_OVERLAY,
  "--radius-sm": RADIUS_SM,
  "--radius-md": RADIUS_MD,
  "--radius-lg": RADIUS_LG,
  "--radius-pill": RADIUS_PILL,
  "--space": SPACE,
  "--shadow-1": SHADOW_1,
  "--shadow-2": SHADOW_2,
  "--font-sans": FONT_SANS,
  "--font-mono": FONT_MONO,
  "--line-height-ar": LINE_HEIGHT_AR,
  "--line-height-en": LINE_HEIGHT_EN,
  "--nav-width": NAV_WIDTH,
  "--nav-width-collapsed": NAV_WIDTH_COLLAPSED,
  "--row-height": ROW_HEIGHT,
  "--topbar-height": TOPBAR_HEIGHT,
  "--control-height": CONTROL_HEIGHT,
  "--control-height-compact": CONTROL_HEIGHT_COMPACT,
  "--control-height-lg": CONTROL_HEIGHT_LG,
  "--icon-button-size": ICON_BUTTON_SIZE,
  "--text-page-title-size": TEXT_PAGE_TITLE_SIZE,
  "--text-page-title-height": TEXT_PAGE_TITLE_HEIGHT,
  "--text-body-size": TEXT_BODY_SIZE,
  "--text-body-height": TEXT_BODY_HEIGHT,
  "--text-label-size": TEXT_LABEL_SIZE,
  "--text-label-height": TEXT_LABEL_HEIGHT,
  "--motion-fast": MOTION_FAST,
  "--motion-panel": MOTION_PANEL,
} as const;

/** CSS custom property names owned by the visual contract. */
export type DesignTokenName = keyof typeof DESIGN_TOKENS;
