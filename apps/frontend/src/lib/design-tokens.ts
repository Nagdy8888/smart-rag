/**
 * Canonical design tokens for the production console.
 *
 * Values must match the Ink & Indigo refresh and `globals.css` `:root`.
 * CSS variables plus this module are the implementation source of truth.
 *
 * @remarks
 * Do not load Google Fonts or Tailwind from a CDN. Motion honors
 * `prefers-reduced-motion`. `--gradient-brand` is reserved for the auth
 * brand panel, empty-state icon tile, and nav brand logo tile.
 */

/** Page canvas. Not lavender `#faf8ff`. */
export const COLOR_BG = "#F6F7F9";

/** Card, drawer, topbar, nav, and input surface. */
export const COLOR_SURFACE = "#FFFFFF";

/** Secondary panels, table headers, code blocks. */
export const COLOR_SURFACE_MUTED = "#F1F3F6";

/** Neutral hover fill. */
export const COLOR_SURFACE_HOVER = "#EDEFF4";

/** Selected navigation or list row. */
export const COLOR_SURFACE_SELECTED = "#EEF2FF";

/** Primary body text. Never pure black. */
export const COLOR_TEXT = "#101828";

/** Secondary body text. */
export const COLOR_TEXT_SECONDARY = "#475467";

/** Metadata and helper text. */
export const COLOR_TEXT_MUTED = "#667085";

/** Disabled text only. */
export const COLOR_TEXT_DISABLED = "#98A2B3";

/** Default borders. */
export const COLOR_BORDER = "#E4E7EC";

/** Emphasized separators and input hover. */
export const COLOR_BORDER_STRONG = "#CBD5E1";

/** Primary action and active navigation. */
export const COLOR_ACCENT = "#4F46E5";

/** Primary hover. */
export const COLOR_ACCENT_HOVER = "#4338CA";

/** Primary pressed. */
export const COLOR_ACCENT_PRESSED = "#3730A3";

/** Text on primary fills. */
export const COLOR_ACCENT_FG = "#FFFFFF";

/** Selected / muted accent fill. */
export const COLOR_ACCENT_MUTED = "#EEF2FF";

/** Alias of muted accent for existing callers. */
export const COLOR_ACCENT_SOFT = "#EEF2FF";

/** Selected outline. */
export const COLOR_ACCENT_BORDER = "#C7D2FE";

/** Dark ink navigation rail background. */
export const COLOR_INK = "#0F1420";

/** Nav hover/active surface. */
export const COLOR_INK_RAISED = "#1A2132";

/** Nav rail border. */
export const COLOR_INK_BORDER = "#232B3E";

/** Light text on the ink rail. */
export const COLOR_INK_TEXT = "#E2E6EF";

/** Muted text on the ink rail. */
export const COLOR_INK_TEXT_MUTED = "#8E97AB";

/** Brand moments only: auth panel, empty-state tile, nav logo tile. */
export const GRADIENT_BRAND = "linear-gradient(135deg, #4F46E5 0%, #7C3AED 100%)";

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
export const COLOR_FOCUS = "#4F46E5";

/** Modal overlay. No blur. */
export const COLOR_OVERLAY = "rgb(15 23 42 / 0.42)";

/** Control radius (buttons, inputs). */
export const RADIUS_CONTROL = "10px";

/** Card, panel, dialog radius. */
export const RADIUS_CARD = "14px";

/** Control radius alias used by existing CSS. */
export const RADIUS_SM = "10px";

/** Card radius alias used by existing CSS. */
export const RADIUS_MD = "14px";

/** Overlay radius (same as cards). */
export const RADIUS_LG = "14px";

/** Status pill radius. */
export const RADIUS_PILL = "999px";

/** Spacing grid unit. */
export const SPACE = "4px";

/** Resting elevation. */
export const SHADOW_1 = "0 1px 3px rgb(16 24 40 / 0.10)";

/** Dialog and drawer elevation. */
export const SHADOW_2 = "0 12px 32px rgb(16 24 40 / 0.14)";

/** Floating composer card elevation. */
export const SHADOW_COMPOSER = "0 8px 24px rgb(16 24 40 / 0.12)";

/** Self-hosted Inter plus system Arabic fallbacks. */
export const FONT_SANS =
  '"Inter", "Segoe UI", "IBM Plex Sans Arabic", "Noto Naskh Arabic", sans-serif';

/** Display headings. */
export const FONT_DISPLAY = '"Inter Display", Inter, "Segoe UI", sans-serif';

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
export const TEXT_BODY_HEIGHT = "22px";

/** Hero heading size. */
export const TEXT_HERO_SIZE = "32px";

/** Hero heading line height. */
export const TEXT_HERO_HEIGHT = "40px";

/** Section heading size. */
export const TEXT_SECTION_SIZE = "18px";

/** Section heading line height. */
export const TEXT_SECTION_HEIGHT = "26px";

/** Card title size. */
export const TEXT_CARD_TITLE_SIZE = "15px";

/** Card title line height. */
export const TEXT_CARD_TITLE_HEIGHT = "22px";

/** Meta caption size. */
export const TEXT_META_SIZE = "12px";

/** Meta caption line height. */
export const TEXT_META_HEIGHT = "16px";

/** Label size. */
export const TEXT_LABEL_SIZE = "13px";

/** Label line height. */
export const TEXT_LABEL_HEIGHT = "18px";

/** Hover/focus transition. */
export const MOTION_FAST = "150ms ease-out";

/** Drawer/dialog transition. */
export const MOTION_DRAWER = "200ms ease-out";

/** Drawer/dialog transition alias for existing CSS. */
export const MOTION_PANEL = "200ms ease-out";

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
  "--color-ink": COLOR_INK,
  "--color-ink-raised": COLOR_INK_RAISED,
  "--color-ink-border": COLOR_INK_BORDER,
  "--color-ink-text": COLOR_INK_TEXT,
  "--color-ink-text-muted": COLOR_INK_TEXT_MUTED,
  "--gradient-brand": GRADIENT_BRAND,
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
  "--radius-control": RADIUS_CONTROL,
  "--radius-card": RADIUS_CARD,
  "--radius-sm": RADIUS_SM,
  "--radius-md": RADIUS_MD,
  "--radius-lg": RADIUS_LG,
  "--radius-pill": RADIUS_PILL,
  "--space": SPACE,
  "--shadow-1": SHADOW_1,
  "--shadow-2": SHADOW_2,
  "--shadow-composer": SHADOW_COMPOSER,
  "--font-sans": FONT_SANS,
  "--font-display": FONT_DISPLAY,
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
  "--text-hero-size": TEXT_HERO_SIZE,
  "--text-hero-height": TEXT_HERO_HEIGHT,
  "--text-page-title-size": TEXT_PAGE_TITLE_SIZE,
  "--text-page-title-height": TEXT_PAGE_TITLE_HEIGHT,
  "--text-section-size": TEXT_SECTION_SIZE,
  "--text-section-height": TEXT_SECTION_HEIGHT,
  "--text-card-title-size": TEXT_CARD_TITLE_SIZE,
  "--text-card-title-height": TEXT_CARD_TITLE_HEIGHT,
  "--text-body-size": TEXT_BODY_SIZE,
  "--text-body-height": TEXT_BODY_HEIGHT,
  "--text-label-size": TEXT_LABEL_SIZE,
  "--text-label-height": TEXT_LABEL_HEIGHT,
  "--text-meta-size": TEXT_META_SIZE,
  "--text-meta-height": TEXT_META_HEIGHT,
  "--motion-fast": MOTION_FAST,
  "--motion-drawer": MOTION_DRAWER,
  "--motion-panel": MOTION_PANEL,
} as const;

/** CSS custom property names owned by the visual contract. */
export type DesignTokenName = keyof typeof DESIGN_TOKENS;
