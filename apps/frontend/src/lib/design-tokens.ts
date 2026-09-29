/**
 * Canonical design tokens for the production console.
 *
 * Values match The Field (ink field, bone plate, electric citation) and
 * `globals.css` `:root`. CSS variables plus this module are the
 * implementation source of truth.
 *
 * @remarks
 * Do not load Google Fonts or Tailwind from a CDN. Motion honors
 * `prefers-reduced-motion`.
 */

/** Ink field behind every console surface. */
export const COLOR_BG = "#0e1c24";

/** Bone plate for work content. */
export const COLOR_SURFACE = "#f4f1ea";

/** Secondary panels on the plate. */
export const COLOR_SURFACE_MUTED = "#ebe6db";

/** Neutral hover fill. */
export const COLOR_SURFACE_HOVER = "#e3ddd0";

/** Selected navigation or list row. */
export const COLOR_SURFACE_SELECTED = "#d8f82133";

/** Primary body text on the plate. */
export const COLOR_TEXT = "#121417";

/** Secondary body text. */
export const COLOR_TEXT_SECONDARY = "#3a3f44";

/** Metadata and helper text. */
export const COLOR_TEXT_MUTED = "#5c646b";

/** Disabled text only. */
export const COLOR_TEXT_DISABLED = "#8a9298";

/** Default borders. */
export const COLOR_BORDER = "#cfc8bb";

/** Emphasized separators and input hover. */
export const COLOR_BORDER_STRONG = "#121417";

/** Primary action fill. */
export const COLOR_PRIMARY = "#121417";

/** Primary hover fill. */
export const COLOR_PRIMARY_HOVER = "#2a2e33";

/** Primary pressed fill. */
export const COLOR_PRIMARY_PRESSED = "#3d4349";

/** Text on primary fills. */
export const COLOR_PRIMARY_FG = "#f4f1ea";

/** Electric mark for live state and citations. */
export const COLOR_ACCENT = "#d8f821";

/** Primary hover. */
export const COLOR_ACCENT_HOVER = "#c6e41a";

/** Primary pressed. */
export const COLOR_ACCENT_PRESSED = "#b0cc12";

/** Text on accent fills. */
export const COLOR_ACCENT_FG = "#121417";

/** Selected / muted accent fill. */
export const COLOR_ACCENT_MUTED = "#d8f82133";

/** Alias of muted accent for existing callers. */
export const COLOR_ACCENT_SOFT = "#d8f82122";

/** Selected outline. */
export const COLOR_ACCENT_BORDER = "#d8f821";

/** Citations and provenance only. */
export const COLOR_EVIDENCE = "#d8f821";

/** Evidence hover. */
export const COLOR_EVIDENCE_HOVER = "#c6e41a";

/** Evidence muted fill. */
export const COLOR_EVIDENCE_MUTED = "#d8f82133";

/** Ink field behind the plate. */
export const COLOR_FIELD = "#0e1c24";

/** Text and links on the ink field. */
export const COLOR_FIELD_FG = "#f4f1ea";

/** Bone plate surface alias. */
export const COLOR_PLATE = "#f4f1ea";

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
export const COLOR_FOCUS = "#d8f821";

/** Modal overlay. No blur. */
export const COLOR_OVERLAY = "rgb(14 28 36 / 0.55)";

/** Control radius (buttons, inputs). */
export const RADIUS_CONTROL = "12px";

/** Card and panel radius. */
export const RADIUS_CARD = "24px";

/** Control radius alias used by existing CSS. */
export const RADIUS_SM = "12px";

/** Card radius alias used by existing CSS. */
export const RADIUS_MD = "24px";

/** Overlay radius. */
export const RADIUS_LG = "28px";

/** Status pill radius. */
export const RADIUS_PILL = "999px";

/** Spacing grid unit. */
export const SPACE = "4px";

/** Resting surfaces have a border and no shadow. */
export const SHADOW_1 = "none";

/** Dialog and drawer elevation. */
export const SHADOW_2 = "0 16px 40px rgb(8 23 39 / 0.35)";

/** Self-hosted IBM Plex Sans plus Arabic companion. */
export const FONT_SANS =
  '"IBM Plex Sans", "IBM Plex Sans Arabic", "Segoe UI", "Noto Naskh Arabic", sans-serif';

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
export const TEXT_PAGE_TITLE_SIZE = "20px";

/** Page title line height. */
export const TEXT_PAGE_TITLE_HEIGHT = "28px";

/** Body size. */
export const TEXT_BODY_SIZE = "14px";

/** Body line height. */
export const TEXT_BODY_HEIGHT = "22px";

/** Hero heading size. */
export const TEXT_HERO_SIZE = "28px";

/** Hero heading line height. */
export const TEXT_HERO_HEIGHT = "36px";

/** Section heading size. */
export const TEXT_SECTION_SIZE = "16px";

/** Section heading line height. */
export const TEXT_SECTION_HEIGHT = "24px";

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

/** Hover and focus transition. */
export const MOTION_FAST = "150ms cubic-bezier(0.22, 1, 0.36, 1)";

/** Drawer and dialog transition. */
export const MOTION_DRAWER = "250ms cubic-bezier(0.22, 1, 0.36, 1)";

/** Drawer and dialog transition alias for existing CSS. */
export const MOTION_PANEL = "250ms cubic-bezier(0.22, 1, 0.36, 1)";

/** Per-item stagger offset. */
export const DURATION_STAGGER = "40ms";

/** Press feedback, tooltip delay, and the delay before a secondary line. */
export const DURATION_MICRO = "80ms";

/** Hover and focus transitions, backdrops, text swaps, and small rows. */
export const DURATION_QUICK = "150ms";

/** Dialogs, menus, tabs, bubbles, list rows, banners, and page fades. */
export const DURATION_FAST = "250ms";

/** Side sheets, the auth form entrance, and the evidence bar. */
export const DURATION_SLOW = "400ms";

/** Meters and progress bars filling. */
export const DURATION_VERY_SLOW = "500ms";

/** Curve for everything that opens, slides, grows, or moves. */
export const EASE_SMOOTH_OUT = "cubic-bezier(0.22, 1, 0.36, 1)";

/** Curve for fades, text swaps, and loops. */
export const EASE_IN_OUT = "ease-in-out";

/** Slight overshoot, only for citation markers and count changes. */
export const EASE_BOUNCE = "cubic-bezier(0.34, 1.36, 0.64, 1)";

/** Shortest translate distance. */
export const DISTANCE_MICRO = "4px";

/** Medium translate distance. */
export const DISTANCE_SMALL = "6px";

/** Default translate distance. */
export const DISTANCE_BASE = "8px";

/** Dialog entrance scale. */
export const SCALE_LARGE = "0.96";

/** Menu and popover entrance scale. */
export const SCALE_MEDIUM = "0.97";

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
  "--color-primary": COLOR_PRIMARY,
  "--color-primary-hover": COLOR_PRIMARY_HOVER,
  "--color-primary-pressed": COLOR_PRIMARY_PRESSED,
  "--color-primary-fg": COLOR_PRIMARY_FG,
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
  "--color-field": COLOR_FIELD,
  "--color-field-fg": COLOR_FIELD_FG,
  "--color-plate": COLOR_PLATE,
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
  "--duration-stagger": DURATION_STAGGER,
  "--duration-micro": DURATION_MICRO,
  "--duration-quick": DURATION_QUICK,
  "--duration-fast": DURATION_FAST,
  "--duration-slow": DURATION_SLOW,
  "--duration-very-slow": DURATION_VERY_SLOW,
  "--ease-smooth-out": EASE_SMOOTH_OUT,
  "--ease-in-out": EASE_IN_OUT,
  "--ease-bounce": EASE_BOUNCE,
  "--distance-micro": DISTANCE_MICRO,
  "--distance-small": DISTANCE_SMALL,
  "--distance-base": DISTANCE_BASE,
  "--scale-large": SCALE_LARGE,
  "--scale-medium": SCALE_MEDIUM,
} as const;

/** CSS custom property names owned by the visual contract. */
export type DesignTokenName = keyof typeof DESIGN_TOKENS;
