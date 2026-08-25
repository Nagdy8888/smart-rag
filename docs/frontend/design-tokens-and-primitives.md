# Design tokens and primitives

Canonical live values are the Ink & Indigo refresh in
[ADR-ink-indigo-visual-refresh.md](../adr/ADR-ink-indigo-visual-refresh.md)
(user-approved 2026-08-25). That ADR supersedes the Precision Workspace
hex table in
[.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-visual-contract.md](../../.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-visual-contract.md).
`:root` in `apps/frontend/src/app/globals.css` and
`apps/frontend/src/lib/design-tokens.ts` are the only token tables.
Primitives live under `apps/frontend/src/components/ui/` (`Button` /
`PrimaryAction` / `AsyncButton`, `PageHeader`, `ConfirmDialog`,
`EmptyState`, and the existing Input/Table/Sheet set).

## Token contract

### Styling architecture

- Use the existing CSS-variable theme in `apps/frontend/src/app/globals.css` and route/component CSS Modules.
- New visual styles go in the owning `*.module.css`; global resets, font faces, theme variables, focus treatment, and reduced-motion rules stay in `globals.css`.
- Do not use inline `style` for fixed visual design values. Inline style is allowed only for runtime geometry such as graph coordinates or measured progress from a real numeric contract.
- Do not add styled-components, Emotion, Material UI, Chakra, shadcn, Bootstrap, another icon package, or a second token system.
- Tailwind remains build-time infrastructure, but new components use CSS Modules and canonical variables rather than long ad-hoc utility strings.
- Use the existing `Icon` abstraction and installed Lucide icons. No emoji, Material Symbols, remote icon font, custom decorative SVG pack, or text pretending to be an icon.
- Use semantic HTML first: `button`, `a`, `nav`, `main`, `aside`, `header`, `section`, `form`, `fieldset`, `table`, `dialog`, `details`, and headings in order.

### Exact color theme

Set or retain these exact CSS variables:

- `--color-bg: #F6F7F9` — application canvas.
- `--color-surface: #FFFFFF` — cards, drawers, topbar, inputs.
- `--color-surface-muted: #F1F3F6` — secondary panels, table headers, code blocks.
- `--color-surface-hover: #EDEFF4` — neutral hover.
- `--color-surface-selected: #EEF2FF` — selected list item.
- `--color-text: #101828` — primary text.
- `--color-text-secondary: #475467` — secondary body text.
- `--color-text-muted: #667085` — metadata and helper text.
- `--color-text-disabled: #98A2B3` — disabled text only.
- `--color-border: #E4E7EC` — normal borders.
- `--color-border-strong: #CBD5E1` — emphasized separators and input hover.
- `--color-accent: #4F46E5` — primary action.
- `--color-accent-hover: #4338CA` — primary hover.
- `--color-accent-pressed: #3730A3` — primary pressed.
- `--color-accent-fg: #FFFFFF` — text on primary action.
- `--color-accent-muted: #EEF2FF` — active/selected background.
- `--color-accent-border: #C7D2FE` — selected outline.
- `--color-ink: #0F1420` — navigation rail background.
- `--color-ink-raised: #1A2132` — nav hover/active.
- `--color-ink-border: #232B3E`.
- `--color-ink-text: #E2E6EF`.
- `--color-ink-text-muted: #8E97AB`.
- `--color-evidence: #0E8584` — citations and evidence accents.
- `--color-evidence-hover: #0A6F6E`.
- `--color-evidence-muted: #ECFDFC`.
- `--color-success: #166534`.
- `--color-success-bg: #F0FDF4`.
- `--color-success-border: #BBF7D0`.
- `--color-warning: #A16207`.
- `--color-warning-bg: #FFFBEB`.
- `--color-warning-border: #FDE68A`.
- `--color-danger: #B91C1C`.
- `--color-danger-hover: #991B1B`.
- `--color-danger-bg: #FEF2F2`.
- `--color-danger-border: #FECACA`.
- `--color-info: #1D4ED8`.
- `--color-info-bg: #EFF6FF`.
- `--color-info-border: #BFDBFE`.
- `--color-focus: #4F46E5`.
- `--color-overlay: rgb(15 23 42 / 0.42)` — modal/sheet overlay, with no blur.

Rules:

- `--gradient-brand` may appear only on the auth brand panel, empty-state icon tile, and nav logo tile. No other gradients. Skeleton shimmer is the one loading exception.
- No glass, transparency-based cards, or `backdrop-filter`.
- No pure black text.
- White text is used only on accent/danger fills that pass WCAG AA.
- Evidence teal is reserved for citations/provenance, not ordinary buttons.
- Success, warning, and danger are never the only status signal; include text and an icon.

### Exact typography

Font families:

- Body: locally hosted `Inter`, weights 400, 500, and 600 only.
- Headings: locally hosted `Inter Display` weight 600, then Inter.
- Fallback: `"Segoe UI", "IBM Plex Sans Arabic", "Noto Naskh Arabic", sans-serif`.
- Monospace: `ui-monospace, "Cascadia Code", "SFMono-Regular", Consolas, monospace`.
- Do not download fonts at runtime.

Type scale (size/line-height, weight, letter-spacing):

- Hero: 32/40, 600, `-0.02em`.
- Page title: 24/32, 600, `-0.02em` (Inter Display).
- Auth title: 28/36, 600 (Inter Display).
- Section: 18/26, 600.
- Card title: 15/22, 600.
- Body: 14/22, 400.
- Label: 13/18, 600.
- Meta: 12/16, 400, muted.
- Code/identifier: 12/18, 500, monospace.
- Arabic/mixed content uses the same nominal size with `line-height: 1.75`.

Rules:

- Do not use uppercase for sentences, buttons, or navigation.
- Eyebrows may use uppercase only for short categories, with `0.04em` letter spacing.
- Limit ordinary paragraph width to 72 characters where possible.
- Use sentence case everywhere: “Import source,” not “IMPORT SOURCE” or “Import Source.”
- Truncate only metadata in constrained rows. Never truncate an answer, error, filename in a detail view, or citation locator without an accessible full-value affordance.

### Exact spacing, sizing, radius, border, and elevation

Spacing uses a 4px base:

- `4px` icon micro-gap.
- `8px` compact inline gap.
- `12px` control group gap.
- `16px` standard component padding/gap.
- `20px` dense card padding.
- `24px` page section gap and normal card padding.
- `32px` large section gap.
- `40px` auth card vertical spacing.
- `48px` page top/bottom breathing room on desktop.
- `64px` only for major empty-state vertical space.

Geometry:

- Standard button/input/select height: 40px.
- Compact button height: 32px.
- Large/auth primary button height: 44px.
- Icon button: 36px square; compact icon button: 32px square.
- Navigation row: 40px high.
- Enterprise table/list row: minimum 48px high.
- Topbar: 56px high.
- Desktop nav: 232px wide; collapsed nav: 72px.
- Form field maximum width: 520px unless it is search or chat composer.
- Auth card width: 420px maximum.
- Dialog width: 480px default, 640px wide; never exceed `calc(100vw - 32px)`.
- Right drawer width: 440px default, 560px for source/detail content; mobile uses full width.

Radius:

- Buttons, inputs, selects, search, compact controls: 10px (`--radius-control`).
- Cards, panels, banners, menus: 14px (`--radius-card`).
- Dialogs and drawers: 14px.
- Composer card: 16px.
- Avatar: 50% circle.
- Status pills and small filter chips: 999px.
- Do not make ordinary buttons pill-shaped.

Borders/elevation:

- Standard border: `1px solid var(--color-border)`.
- Strong/hover border: `1px solid var(--color-border-strong)`.
- Selected border: `1px solid var(--color-accent-border)`.
- `--shadow-1: 0 1px 3px rgb(16 24 40 / 0.10)` for raised cards and menus.
- `--shadow-2: 0 12px 32px rgb(16 24 40 / 0.14)` for dialogs and drawers.
- `--shadow-composer: 0 8px 24px rgb(16 24 40 / 0.12)` for the Ask composer.
- Never stack multiple shadows or use glow effects.

### Motion and feedback

- Hover/focus color transitions: `150ms ease-out` (`--motion-fast`). Color, background, border, and box-shadow only.
- Drawer/dialog open/close: `200ms ease-out`, opacity plus at most 8px translation.
- Do not animate layout height while progress events arrive or when the verified answer is inserted.
- Spinner rotation is allowed. Skeleton shimmer (1.2s sweep) is the only loading gradient.
- Under `prefers-reduced-motion: reduce`, transitions become effectively immediate and spinners may remain a static labeled state.
- Button press feedback uses color change, not scale/bounce.
- Async work always changes visible label/state immediately and disables only the action being submitted.

### Responsive breakpoints and page frame

Use these exact behavior breakpoints:

- `>= 1280px`: full 232px nav, 24px main padding, multi-pane layouts enabled.
- `1024px–1279px`: collapsed 72px nav by default, 20px main padding, graph inspector becomes drawer.
- `768px–1023px`: no persistent nav; mobile/tablet topbar and left navigation sheet, 20px main padding, two-pane layouts collapse.
- `< 768px`: 16px main padding, full-width controls, sheets use full viewport width, tables become horizontally scrollable labeled regions or semantic cards.
- Verification widths are exactly 390px, 768px, 1024px, and 1280px.

Global frame:

- Body background is `--color-bg`; primary content surfaces are white.
- Topbar is sticky at top with white background and bottom border; no shadow unless content scrolls beneath it.
- Main region maximum width is 1440px and centered, except Chat and Graph may use all available width.
- Normal page vertical gap is 24px.
- Every page starts with one `PageHeader`; do not repeat the page title inside the first card.

### Primitive component specification

#### `Button`

An ordinary rounded rectangle, never a decorative shape.

- Default: 40px high, 8px radius, 14px/20px weight 600, 14px horizontal padding, 8px icon gap.
- Primary: accent background, white text, no border. Hover accent-hover; pressed accent-pressed.
- Secondary: white background, primary text, normal border. Hover surface-hover with strong border.
- Ghost: transparent background, primary text. Hover surface-hover. Use only in toolbars/menus.
- Danger: danger background, white text. Hover danger-hover. Use only after a confirmation boundary.
- Quiet danger: transparent, danger text; hover danger-bg. Use for opening a delete confirmation, not final confirmation.
- Loading: keep width stable, show 16px spinner before label, label becomes a present participle such as “Sending…” or “Deleting…”.
- Disabled: disabled surface, disabled text, normal border, `cursor: not-allowed`; a visible adjacent reason or tooltip is mandatory.
- Focus: 2px focus ring with 2px offset.
- Icons are 16px. A trailing chevron is allowed only when opening a menu/disclosure.

#### `IconButton`

- 36px square, 8px radius, ghost style by default.
- Must have `aria-label`; tooltip repeats the action label on hover/focus.
- Icon is 18px.
- Never use an unlabeled icon for a destructive action.

#### `LinkButton`

- Must render a real `Link`/anchor, not a button that navigates.
- It may visually match Primary or Secondary.
- External links show an external-link icon and safe `rel`.

#### `AsyncButton`

- Wrap existing `Button`; accept `pending`, `pendingLabel`, and real disabled reason.
- Prevent duplicate submit.
- Do not swallow errors or show success itself; owning form renders an inline status.

#### `Input`, `Select`, and `SearchInput`

- 40px high, white background, 8px radius, 1px border, 12px horizontal padding.
- Label sits 6px above, 13px/18px weight 600.
- Placeholder uses muted text and is never the only label.
- Hover uses strong border; focus uses accent border plus focus ring.
- Error uses danger border, danger helper text, and `aria-describedby`.
- Disabled uses muted background; readonly uses surface-muted but normal text.
- Search input has a 16px leading search icon and a real clear button only when non-empty.

#### `Textarea`

- Same visual contract as Input.
- Normal minimum height 104px.
- Chat composer minimum 52px and maximum 180px, auto-resizing; after max height it scrolls internally.
- Character counter appears only after 80% of the server limit.

#### `Checkbox`

- Native input retained for accessibility.
- Visual box is 18px square, 4px radius, accent checked state.
- Entire label row has at least 40px hit height.
- Helper/error text aligns with label text, not the box.

#### `Tabs`

- Use for Admin sections and list/canvas switching only.
- Horizontal tab list with 40px tab height.
- Active tab has accent text and a 2px bottom border; inactive tabs have secondary text.
- No pill-style segmented tabs for page-level navigation.
- Arrow keys move focus; Home/End supported.
- URL-addressable page tabs update the query string.

#### `Menu`

- White 12px-radius surface, 1px border, shadow-1, 8px vertical padding.
- Item height 36px, 12px horizontal padding, 8px icon gap.
- Destructive item is danger text and separated by a divider.
- Escape closes; focus returns to trigger; arrows navigate.

#### `Tooltip`

- Use only to supplement icon controls or explain temporary disabled state.
- Dark ink background, white 12px text, 6px radius, 6px by 8px padding.
- Delay 400ms; appears on keyboard focus immediately.
- Never place essential error/help content only in a tooltip.

#### `Card` and `Panel`

- White background, 12px radius, 1px border.
- Standard padding 24px; dense card 16px or 20px.
- Shadow is absent by default. Use shadow-1 only for clearly raised interactive cards.
- Header has title left and at most one primary/overflow action right.
- Do not nest more than one bordered card inside another.

#### `StatusPill`

- 24px high, 999px radius, 12px/16px weight 600, 8px horizontal padding, 6px gap.
- Includes a 6px dot or 14px status icon plus text.
- Ready/complete: success text on success background.
- Processing/running: info text on info background.
- Pending/queued/degraded: warning text on warning background.
- Failed/blocked/quarantined: danger text on danger background.
- Neutral/unknown: secondary text on surface-muted with border.
- Unknown server values render neutral exact safe text; do not invent a status.

#### `StatusBanner`

- Full available width, 12px radius, 1px semantic border, 12px by 16px padding.
- Layout: 18px icon, title/body, optional one action aligned right on desktop and below on mobile.
- Info, success, warning, and error use the exact semantic color triples above.
- Error banners use `role="alert"` only for blocking/new failures; ordinary persisted information uses `role="status"`.
- No dismiss control for a condition that still blocks the action.

#### `Badge` and `FilterChip`

- Badge is non-interactive metadata, 22px high.
- FilterChip is interactive only when it visibly toggles a filter and uses `aria-pressed`.
- Do not style route navigation as chips.

#### `DataTable`

- Semantic table with sticky header when the list scrolls.
- Header: 40px high, muted surface, 12px/16px weight 600, left aligned except numeric columns.
- Row: minimum 48px, white background, bottom border, hover surface-hover only if row is actionable.
- First column contains the primary identity/link.
- Status is a pill; timestamps are secondary text; actions are one overflow IconButton.
- Sortable header is a real button with direction icon and accessible state.
- On mobile, retain a semantic scroll region or render cards with the same field labels; do not hide critical fields without a detail path.

#### `Pagination`

- Use “Load more” for cursor lists, not numbered pages.
- Secondary button centered below list.
- While loading, label “Loading…” and preserve existing rows.
- Hide when fewer than the page size are returned.
- Failure appears inline with Retry using the same cursor.

#### `EmptyState`

- Centered within a minimum 240px region.
- 40px muted icon in a 56px accent-muted square with 12px radius.
- Title 16px/24px weight 600; body 14px, max width 420px.
- At most one primary and one secondary action, both real.
- Do not include illustrations or stock images.

#### `ErrorState`

- Same geometry as EmptyState but uses danger-muted icon treatment.
- Generic title “Something went wrong.”
- Safe route-specific body.
- Retry appears only when retry is valid; never expose exception text.

#### `Skeleton` and `Spinner`

- Skeleton uses solid `#E9EDF2` blocks with 8px radius. Optional subtle opacity animation only when reduced motion is not requested.
- Match final layout dimensions to prevent shift.
- Spinner is 16px or 20px with accessible adjacent text; a spinner alone is never the only status.

#### `Dialog` and `ConfirmDialog`

- Centered white surface, 12px radius, shadow-2, overlay with no blur.
- Header 20px title; body 14px; footer right-aligned buttons with Cancel before primary.
- Destructive confirmation names the object and consequence.
- Initial focus goes to Cancel for destructive actions; final destructive button uses Danger.
- Escape/click outside closes only when no irreversible request is pending.

#### `Sheet` and `Drawer`

- White surface, 12px left-side radius on desktop right drawers; no radius on full-width mobile.
- Header is sticky, 56px high, title left, close IconButton right.
- Body 20px padding; footer sticky only when actions are required.
- Overlay has no blur. Escape and overlay click close when safe.
- Focus is trapped and returned to trigger.

#### `FileDropZone`

- Minimum 160px high, 12px radius, 1px dashed strong border, surface-muted background.
- Centered upload icon, title “Drop files here,” body “or choose files,” and one Secondary “Choose files” button.
- Drag-over uses accent-muted background and accent border.
- Show exact accepted formats and 100 MB server cap beneath.
- Selected files become a real queue with filename, bytes, stage, error, and Remove before upload.
- Never show fabricated percentage for parsing/indexing.

#### `LiveRegion`

- One polite region for progress/reconnect/status summaries and one assertive region for blocking errors.
- Announce stage changes, reconnect, verified answer availability, terminal, and errors; do not announce each compatibility answer chunk.

#### `UserText`, `LogicalHighlight`, and hostile content

- Render as React text nodes only.
- Use `dir="auto"` and bidi isolation.
- Preserve canonical logical offsets.
- Never convert model/retrieved markdown to HTML in this overhaul.
