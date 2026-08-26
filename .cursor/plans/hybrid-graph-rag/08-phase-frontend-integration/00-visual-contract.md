---
phase: 8
status: active
title: Phase 8 visual contract
---

# Phase 8 visual contract

This file is the exact user-approved visual and interaction brief for remediation packets P08-13 through P08-20. Copy values; do not reinterpret them. Security, authorization, API, data, and accessibility contracts still have higher precedence.

## Normative UI/UX implementation specification

This section is the complete visual and interaction brief. The implementation model must not perform another design search, choose a different theme, install a component library, invent alternate tokens, or reinterpret the layout. Repository inspection is still required to edit safely, but no visual decision is delegated to the implementation model.

If an old screenshot, Stitch frame, component style, or prose document conflicts with this section, this user-approved specification wins for the overhaul. Security, authorization, API, data, and accessibility contracts still have higher precedence.

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

- `--color-bg: #F4F6F8` — application canvas.
- `--color-surface: #FFFFFF` — cards, drawers, topbar, nav, inputs.
- `--color-surface-muted: #F8FAFC` — secondary panels, table headers, code blocks.
- `--color-surface-hover: #F1F4F8` — neutral hover.
- `--color-surface-selected: #EEF0FF` — selected navigation/list item.
- `--color-text: #182230` — primary text.
- `--color-text-secondary: #475467` — secondary body text.
- `--color-text-muted: #637083` — metadata and helper text.
- `--color-text-disabled: #8A94A3` — disabled text only.
- `--color-border: #DDE3EA` — normal borders.
- `--color-border-strong: #C7D0DB` — emphasized separators and input hover.
- `--color-accent: #4E5BD5` — primary action and active navigation.
- `--color-accent-hover: #414CC4` — primary hover.
- `--color-accent-pressed: #343DA8` — primary pressed.
- `--color-accent-fg: #FFFFFF` — text on primary action.
- `--color-accent-muted: #EEF0FF` — active/selected background.
- `--color-accent-border: #C9CDF8` — selected outline.
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
- `--color-focus: #4E5BD5`.
- `--color-overlay: rgb(15 23 42 / 0.42)` — modal/sheet overlay, with no blur.

Rules:

- No gradients.
- No glass, transparency-based cards, or `backdrop-filter`.
- No pure black text.
- White text is used only on accent/danger fills that pass WCAG AA.
- Evidence teal is reserved for citations/provenance, not ordinary buttons.
- Success, warning, and danger are never the only status signal; include text and an icon.

### Exact typography

Font families:

- Primary: locally hosted `Inter`, weights 400, 500, and 600 only.
- Fallback: `"Segoe UI", "IBM Plex Sans Arabic", "Noto Naskh Arabic", sans-serif`.
- Monospace: `ui-monospace, "Cascadia Code", "SFMono-Regular", Consolas, monospace`.
- Do not download fonts at runtime. Do not use a decorative display font.

Type scale:

- Page title: 24px size, 32px line-height, weight 600, letter-spacing `-0.01em`.
- Auth title: 28px size, 36px line-height, weight 600, letter-spacing `-0.015em`.
- Section title: 20px size, 28px line-height, weight 600.
- Card title: 16px size, 24px line-height, weight 600.
- Body: 14px size, 20px line-height, weight 400.
- Body strong: 14px size, 20px line-height, weight 600.
- Label: 13px size, 18px line-height, weight 600.
- Secondary/meta: 13px size, 18px line-height, weight 400.
- Caption/eyebrow: 12px size, 16px line-height, weight 500.
- Code/identifier: 12px size, 18px line-height, weight 500, monospace.
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

- Buttons, inputs, selects, search, compact controls: 8px.
- Cards, panels, banners, menus: 12px.
- Dialogs and drawers: 12px.
- Avatar: 50% circle.
- Status pills and small filter chips: 999px.
- Do not make ordinary buttons pill-shaped.

Borders/elevation:

- Standard border: `1px solid var(--color-border)`.
- Strong/hover border: `1px solid var(--color-border-strong)`.
- Selected border: `1px solid var(--color-accent-border)`.
- `--shadow-1: 0 1px 2px rgb(15 23 42 / 0.08)` for raised cards and menus.
- `--shadow-2: 0 8px 24px rgb(15 23 42 / 0.10)` for dialogs and drawers.
- Never stack multiple shadows or use glow effects.

### Motion and feedback

- Hover/focus color transitions: 120ms ease-out.
- Drawer/dialog open/close: 160ms ease-out, opacity plus at most 8px translation.
- Do not animate layout height while progress events arrive or when the verified answer is inserted.
- Spinner rotation is allowed; pulsing decorative gradients are forbidden.
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

### Application shell component specification

#### `AppShell`

- Desktop grid columns are `232px minmax(0, 1fr)`; collapsed mode is `72px minmax(0, 1fr)`.
- Nav and topbar are white with border separators.
- Main area uses canvas background and owns vertical scrolling.
- Skip link is visually hidden until focused, then appears at top-left as a Primary-style link.
- No footer is needed.

#### Brand block

- Height 56px, 16px horizontal padding.
- 28px square accent mark with existing spark icon and 8px radius.
- “Smart RAG” 14px/20px weight 600; “Company knowledge” 12px muted.
- Collapsed nav shows mark only with tooltip.

#### `AppNav`

- Exact primary order: Ask, Documents, Tables, Graph.
- Admin is separated by a 16px gap and shown only for owner/admin.
- Row is 40px high, 8px horizontal margin, 8px radius, 12px horizontal inner padding.
- Icon 18px, label 14px weight 500, gap 10px.
- Active: accent-muted background, accent text, and a 3px accent bar inset at left.
- Hover: surface-hover. No hover movement.
- Collapsed: centered icons, labels visually hidden, tooltips enabled.
- Mobile sheet uses full labels and no collapsed mode.

#### `ConsoleTopbar`

- Sticky 56px white bar with bottom border.
- Left: mobile menu button when needed, then one page title.
- Right order: readiness control, command control, Account control.
- Do not repeat logo in the topbar when desktop nav is visible.
- At 390px, hide command control first; keep readiness and Account.

#### `ReadinessIndicator`

- It is a button because it opens a real popover.
- Labels: “Checking,” “Ready,” “Degraded,” or “Unavailable.”
- Use corresponding neutral/success/warning/danger pill styling.
- Popover width 320px. Show “Question answering,” “Keyword search,” and “Graph search” only when real readiness fields authorize those labels.
- Primary blocking copy: “Question answering is temporarily unavailable. Try again when the service is ready.”
- Never expose DSNs, provider names not authorized for the caller, stack traces, or probe credentials.

#### `AccountMenu`

- Trigger is a 36px IconButton containing a generated two-letter initial avatar; no remote avatar.
- Menu shows email, role badge, upload capability text, Account details, and Sign out.
- No MFA field, profile editor, locale editor, or company settings.
- Sign out is separated as a quiet-danger menu item.

#### `CommandMenu`

- Dialog width 560px.
- Search input at top; results show supported routes only.
- Each result has icon, label, and optional short description.
- Keyboard: Ctrl/Cmd+K opens, arrows move, Enter navigates, Escape closes.
- Do not include actions that submit mutations.

#### `PageHeader`

- Desktop: title/description left, one primary action right.
- Mobile: stacked, action full width only when it is the page’s main task.
- Title uses Page title style; description uses secondary body, max width 720px.
- Bottom margin 24px.

### Auth component and page specification

#### `AuthLayout`

- Full viewport canvas with centered content.
- Brand above card with 32px bottom gap.
- Auth card: width 420px, white, 12px radius, border, shadow-1, 32px padding desktop and 24px mobile.
- No split-screen marketing panel, stock art, gradient, testimonial, or decorative background.

#### `AuthCard`

- Title, one-sentence helper, form, then text links.
- Form fields separated by 16px.
- Primary submit is full width, 44px high.
- Secondary navigation is plain text link beneath with 16px top margin.
- Inline error banner sits above fields and receives focus after failure.

Exact pages:

- Sign in title: “Sign in to Smart RAG.” Helper: “Use your company account to access private knowledge.”
- Sign up title: “Create your account.” Helper: “Your account still needs a valid company invitation.”
- Forgot title: “Reset your password.” Helper: “We’ll send a reset link to your email.”
- Reset title: “Choose a new password.”
- Invitation title: “Accept invitation.” Helper: “Sign in with the email address that received this invitation.”
- Callback page shows Spinner plus “Completing sign in…” and a safe timeout error with “Return to sign in.”
- No Google button, MFA/TOTP page, recovery page, owner-bootstrap page, or unavailable-gap page.

### Ask workspace component specification

#### Overall layout

- Use available height below topbar: `min-height: calc(100dvh - 56px)`.
- At `>=1280px`: 248px Sessions rail and `minmax(0, 1fr)` main workspace, 16px gap.
- At `<1280px`: Sessions rail becomes a left Sheet opened by a “Sessions” Secondary button.
- Main answer column max width is 880px and centered inside available space.
- There is no permanent right sources/diagnostics column.

#### `SessionRail`

- White bordered panel, 12px radius, vertical layout.
- Header: “Sessions” and compact Primary “New” button.
- Search is omitted because the API does not provide global search and local first-page search is misleading.
- Session row: 48px minimum, title one line, created timestamp, current indicator, overflow menu.
- Clicking row performs real Continue. Active row uses selected background.
- Overflow contains Delete only.
- Footer may contain Load more when cursor data supports it.
- Empty copy: “No sessions yet. Start a question to create one.”
- Continuing copy above transcript: “Continuing this session. Earlier messages are not available in this client.”

#### Chat empty state

- Icon: spark/search, not a robot avatar.
- Title: “Ask your company knowledge.”
- Body: “Answers use authorized documents and show available evidence.”
- Three prompt-fill chips maximum:
  - “Summarize an uploaded policy”
  - “Compare two documented values”
  - “Find a relationship between entities”
- Chips populate composer only; they never submit.

#### User message

- Align right, maximum width 78%.
- Accent-muted background, 12px radius with 4px bottom-right radius, 12px by 14px padding.
- Text 14px/22px, `dir="auto"`.
- No avatar, timestamp, edit, copy, or retry button unless backed by a contract.

#### Assistant answer

- Full-width transparent surface with a 3px evidence-colored left border and 16px left padding.
- Header row: spark icon, “Answer,” route StatusPill when real, and overflow with real actions only.
- Answer text 15px/24px for reading comfort.
- Do not show a streaming caret or a pre-verification typewriter. Show only server-originated node/tool progress until verification completes. After verification, append verified text immediately to authoritative state and progressively reveal it under ADR-verified-answer-paced-reveal (≤2.5s, ≤90 publications, skip and reduced-motion bypass). Historical messages never replay the animation.
- Partial/cancelled/error retains existing text and adds a StatusBanner below.
- Footer order: citations, feedback, then “Run details” disclosure.

#### `RunProgress`

- Compact horizontal/vertical step list using real started/completed/failed status and tool_progress events only.
- Known stage labels map to: “Preparing,” “Retrieving,” “Generating,” “Verifying,” plus authorized tool keys when executed.
- Unknown stage renders safe neutral exact stage text in details, not as a new primary phase.
- After verification, paced reveal uses “Verified — displaying answer”; it never implies the model is still generating.
- Current stage uses info style; completed stages success; failure danger.
- Do not show percentages.

#### `ChatComposer`

- White bordered panel, 12px radius, shadow-1, 12px padding.
- Textarea borderless inside composer; focus ring surrounds composer container.
- Bottom toolbar: left character count/status; right Attach is absent unless a real chat attachment contract exists; primary Send/Stop at far right.
- Send button: 40px high, label and 16px arrow icon.
- Running state replaces Send with Secondary/quiet-danger “Stop” and square icon.
- `Enter` submits, `Shift+Enter` inserts newline; IME composition never submits.
- Disabled reason appears immediately above composer in a StatusBanner, not only tooltip.
- Draft remains after admission failure; clears only after successful admission.

#### `ReconnectState`

- Warning banner above composer.
- Copy: “Connection interrupted. Reconnecting… attempt X of Y.”
- Actions: “Cancel” and, after automatic ceiling, “Try again.”
- Keep partial answer visible.

#### `CitationChip`

- 28px high evidence-muted pill, evidence text, evidence border, 12px/16px weight 600.
- Label format: `[1] Source` when a safe source label exists; otherwise `[1] Evidence`.
- Opens real Sources drawer.
- No external-link icon unless a safe authorized URL exists in the actual contract.

#### `SourcesDrawer`

- Width 560px desktop, full width mobile.
- Header “Sources.”
- Group citations by safe source identity only when actual provenance supports it.
- Citation card shows index, document/chunk identifiers, page/sheet/range/URL locator fields actually present, and “Source unavailable” status when true.
- No fake excerpt, preview, download, relevance score, or open-source button.

#### `RunDetailsDrawer`

- Width 440px.
- Sections in order: Status, Route, Limitations, Cache/Coverage, Usage, Technical IDs.
- Closed by default.
- “Your usage” labels `/usage/me`; never “Company total.”
- IDs use monospace and Copy buttons with real clipboard feedback.
- No raw traces, prompts, provider secrets, source text, nDCG, or invented latency.

#### `FeedbackPopover`

- Opens from “Give feedback” Secondary button after terminal.
- First choose thumbs up/down, then required server tag Select, optional comment Textarea, Submit.
- Width 360px; actions right aligned.
- Success copy: “Feedback recorded.”
- Failure copy: “Feedback could not be recorded. Try again.”
- Popover remains open on failure.

### Documents page component specification

#### Page layout

- PageHeader title “Documents.”
- Description: “Upload files or add approved websites, then track search and graph readiness.”
- Primary action: “Import source.”
- Toolbar below: loaded-row filter left and count/status summary right.
- Main content is one white bordered DataTable, not multiple dashboard cards.

#### Document table

- Desktop columns: Name, Visibility, Search status, Graph status, Created, Actions.
- Name is the detail Link with document icon; optional ID appears below in monospace only when title is missing.
- Status values come from real document/version status.
- Row overflow menu includes “View details” and owner/admin “Delete.”
- Clicking blank row space does not navigate; only explicit Name link does.
- Mobile card order: Name, two status pills, visibility/created metadata, then overflow.

#### Documents empty state

- Title: “No documents yet.”
- Body: “Import a file or approved website to create searchable company knowledge.”
- Primary “Import source.”

#### `ImportSourceSheet`

- Right drawer width 560px.
- Header “Import source.”
- Two Tabs: “Files” and “Website.” Both map to real APIs.
- File tab: drop zone, selected queue, category Select, attestation Checkbox, Upload button.
- Website tab: URL Input, approved domain Input, optional title, bounded depth/pages controls only if current API exposes them, attestation, “Add website.”
- Keep one stable idempotency key while the same form submission retries.
- On success, close only after showing created document/job IDs or navigate to detail.

#### Upload queue row

- Filename, bytes, stage StatusPill, and Remove before reservation.
- Real stages: “Ready,” “Reserving,” “Uploading,” “Finalizing,” “Queued,” “Failed.”
- Upload byte progress may use a progress bar only if browser/API provides real uploaded bytes.
- Parsing, embedding, BM25, and graph stages use statuses, never fake percent.

#### `IngestionStatus`

- One component used in list/detail.
- Vertical timeline on detail; compact pills on list.
- Ordered labels from real lifecycle: Uploaded, Scanning, Parsing, Search ready, Graph pending/ready/ineligible, Failed, Deletion pending.
- Expandable technical details show scan signature status, OCR, chunks/tables, BM25, queue age, graph handoff, and retry only when fields exist.
- Retry is a real Secondary button visible only when `retry_allowed`.

#### Document detail

- Header: back Link, document title, visibility/status pills, overflow menu.
- Main desktop grid: `minmax(0, 2fr) minmax(280px, 1fr)`.
- Left: processing timeline and real table references.
- Right: metadata definition list and actions to “Inspect in graph” and “Open tables.”
- Delete is in overflow/danger zone, not a large primary button.
- No source preview, download, audit, PII, or raw storage section.

#### Delete confirmation

- Title: “Delete document?”
- Body: `“<safe title>” will be removed from retrieval and scheduled for cleanup. This cannot be undone.`
- Buttons: “Cancel” and Danger “Delete document.”
- Success navigates to Documents and announces “Document deleted.”

### Tables page component specification

#### Layout

- PageHeader title “Tables.”
- Description: “Run bounded calculations on structured data with exact cell provenance.”
- At `>=1024px`: 320px manifest sidebar and main results area; below that manifest picker is a Select.

#### Manifest sidebar

- White bordered panel, 12px radius.
- Header “Available tables.”
- Rows show safe table/sheet identity and document ID metadata.
- Active row uses selected treatment.
- Empty: “No structured tables are available.”

#### Plan builder

- White Card, title “Analysis plan.”
- Field order: Table, Columns, Filters, Aggregation, Group by, Sort, Comparison.
- Optional sections start collapsed and open via real “Add filter,” “Add aggregation,” etc.
- Repeating row has inputs plus labeled Remove IconButton.
- One Primary “Analyze” button at bottom right.
- No raw SQL editor, natural-language fake planner, Export, Save, or Share button.

#### Results

- Header row: “Results,” row count, and Secondary “View provenance” when ranges exist.
- DataTable numeric cells right aligned and use tabular numerals.
- Generated narrative is shown only if returned by an existing typed contract and clearly separated; otherwise omit.
- Empty successful result: “The analysis returned no rows.”

#### Provenance drawer

- Header “Cell provenance.”
- List exact document/version/table/sheet/range fields from response.
- Monospace for cell ranges.
- No fake source link.

### Graph page component specification

#### Layout

- PageHeader title “Graph.”
- Description: “Inspect bounded entities and relationships backed by authorized evidence.”
- At `>=1280px`: 300px search panel, flexible result panel, 320px inspector.
- At 1024–1279px: search plus result; inspector is right Drawer.
- Below 1024px: stacked search, list/canvas result, inspector Drawer.

#### Entity search panel

- SearchInput label “Search entities.”
- Submit/search executes only for trimmed queries meeting current API minimum.
- Results are 48px rows with object type StatusPill, safe ID/name, support metadata.
- Clicking a result selects it and adds a selected entity chip.
- Maximum 12 selected. At limit, show helper “You can inspect up to 12 entities.”
- Selected chips have real Remove controls.
- Depth Select has exact options 1, 2, 3.
- Primary action “Inspect graph.”

#### Result toolbar

- Left: result count and limitation pill.
- Right: Tabs “List” and “Canvas,” then Fit control only in Canvas.
- No Edit, Add relationship, Expand unlimited, Depth 5, Export, or Save buttons.

#### Graph list

- Default accessible representation.
- Each row: object type, object ID, hop, support, and Select.
- Selection opens inspector.
- Empty: “No authorized graph evidence matched this inspection.”

#### React Flow canvas

- White surface with subtle 16px grid dots using border color.
- Nodes: 168px wide, white, 8px radius, 1px border; selected node accent border and accent-muted background.
- Node first line object type caption, second safe object ID, footer hop/support.
- Edges: 1.5px border-strong; selected path evidence color.
- Controls bottom-right: zoom in, zoom out, fit, each labeled IconButton.
- Mini-map is omitted unless it remains legible and accessible at the bounded 200-node limit.
- Node click selects; canvas itself is not an editor.

#### Graph inspector

- Title “Evidence details.”
- Definition list: Type, Object ID, Document ID, Version ID, Chunk ID, Hop, Support.
- Locator cards show page, section path, sheet/range, or safe URL fields that actually exist.
- Limitation banners appear below details.
- No vendor prose or relationship editing.

### Admin component specification

#### Admin frame

- PageHeader title “Admin.”
- Description: “Manage access, tools, retrieval curation, and usage.”
- Horizontal Tabs: Team & access, Tools, Curation, Usage.
- Tab content is one column with maximum width 1120px.
- Member/viewer never see this route in nav; direct page visit renders a safe permission ErrorState after real server confirmation.

#### Team & access

- First Card “Invite user”: email Input, role Select, upload access Checkbox, Primary “Send invitation.”
- Success shows invitation ID and expiry only; never token.
- Second Card “Offboard user”: danger section, user ID Input, consequence copy, quiet-danger “Review offboarding,” then ConfirmDialog.
- No member directory, avatars, owner-bootstrap wizard, MFA/AAL2 copy, or fake invitation list.

#### Tools

- Toolbar: SearchInput and count.
- Tool cards are compact 2-column desktop/1-column mobile.
- Card: name, version, description, enabled StatusPill, permission Select for owner/admin, and real Enable/Disable AsyncButton.
- Full manifest fields open in Drawer through “View details.”
- No tool seeding form in ordinary UI.

#### Curation

- Two Tabs inside content: Glossary and Entity rules.
- Glossary: import form, result/status, then real Approve/Rollback actions.
- Entity rules: DataTable with canonical type, aliases, status, row version, overflow actions Edit/Approve/Revoke.
- “Suggest rule” Secondary action opens Dialog backed by the real suggestions endpoint.
- Edit uses real PATCH and shows conflict banner on stale row version with “Reload rule.”
- No bulk action without an existing endpoint.

#### Usage

- Two metric cards maximum in one row: “Your usage” and owner/admin “Company usage.”
- Each card shows tokens and USD from the real response, using 24px numeric value and 13px label.
- Below: real readiness/rate degradation StatusBanner.
- No charts without time-series data. No budget editor, hard-cap slider, audit panel, forecast, fake trend, or progress bar.

### Remaining reusable component rules

- `ConversationRail` is renamed/implemented as `SessionRail`; do not keep both.
- `IngestionInspector` and `ProcessingTimeline` become one `IngestionStatus`; do not keep duplicated implementations.
- Keep one graph list and one React Flow canvas; delete the custom third SVG neighborhood.
- `CitationDrawer` and `CitationSheet` become one responsive `SourcesDrawer`; do not maintain separate desktop/mobile logic beyond the shared Drawer primitive.
- `ProfileApp`, dedicated Usage/Team/Tools/Curation page bodies, `ReadinessPanel`, gap pages, MFA components, and review fixture route are removed or reduced to redirects as specified.
- A component not named in this target specification is retained only if it is a structural implementation detail required by one named component and has no separate visual behavior. Otherwise remove it after reference checks.

### Target frontend component/file ownership

Use this as the target tree. Reuse and rename existing files where their behavior matches; do not create a second implementation beside an old one.

- `src/components/ui/app-shell.tsx` and `app-shell.module.css`: `AppShell`, responsive frame, skip link, topbar/nav slots.
- `src/components/ui/app-nav.tsx`: `AppNav`, brand block, nav groups, collapse/mobile triggers.
- `src/components/ui/console-topbar.tsx`: `ConsoleTopbar`, title, readiness, command, Account.
- `src/components/ui/readiness-indicator.tsx`: readiness pill/button and popover.
- `src/components/ui/account-menu.tsx`: initials trigger, `/me` summary, Sign out.
- `src/components/ui/command-menu.tsx`: supported-route command navigation.
- `src/components/ui/page-header.tsx`: shared title/description/one-action header.
- `src/components/ui/button.tsx`: Button variants and sizes.
- `src/components/ui/async-button.tsx`: pending/duplicate-submit wrapper.
- `src/components/ui/input.tsx`, `textarea.tsx`, `select.tsx`, `checkbox.tsx`, and `search-input.tsx`: exact form primitive contracts.
- `src/components/ui/tabs.tsx`: accessible tabs and URL-tab helper.
- `src/components/ui/menu.tsx` and `tooltip.tsx`: menus/tooltips.
- `src/components/ui/dialog.tsx`, `confirm-dialog.tsx`, `sheet.tsx`: modal primitives.
- `src/components/ui/status-pill.tsx`, `status-banner.tsx`, and `badge.tsx`: non-interactive state/metadata.
- `src/components/ui/data-table.tsx` and `pagination.tsx`: table and cursor loading.
- `src/components/ui/empty-state.tsx`, `error-state.tsx`, `skeleton.tsx`, and `spinner.tsx`: system states.
- `src/components/ui/file-drop-zone.tsx`: file selection/drop queue entry.
- `src/components/ui/live-region.tsx`, `user-text.tsx`, and `logical-highlight.tsx`: accessibility and hostile text.
- `src/components/chat/chat-app.tsx`: Ask orchestration only; keep network state out of purely visual children.
- `src/components/chat/session-rail.tsx`: list/continue/new/delete session controls.
- `src/components/chat/chat-composer.tsx`: draft, keyboard submit, Send/Stop, disabled reason slot.
- `src/components/chat/answer-surface.tsx`: user message, assistant answer, terminal status, footer actions.
- `src/components/chat/run-progress.tsx`: real stage timeline.
- `src/components/chat/sources-drawer.tsx`: unified citations/evidence.
- `src/components/chat/run-details-drawer.tsx`: diagnostics and usage.
- `src/components/chat/feedback-popover.tsx`: real feedback form.
- `src/components/documents/document-library.tsx`: documents query, pagination, toolbar, table.
- `src/components/documents/document-row.tsx`: responsive row/card rendering.
- `src/components/documents/import-source-sheet.tsx`: Files/Website forms.
- `src/components/documents/upload-queue.tsx`: selected file queue and real stages.
- `src/components/documents/ingestion-status.tsx`: shared compact/timeline status.
- `src/components/documents/document-detail.tsx`: metadata/status/Graph/Tables actions.
- `src/components/tables/tables-app.tsx`: manifest selection, plan state, analyze query.
- `src/components/tables/table-plan-builder.tsx`: bounded typed controls.
- `src/components/tables/table-results.tsx`: deterministic table and empty/error.
- `src/components/tables/provenance-drawer.tsx`: source ranges.
- `src/components/graph/graph-explorer.tsx`: search/selection/inspect orchestration.
- `src/components/graph/entity-search.tsx`: query and selected entity chips.
- `src/components/graph/graph-result-toolbar.tsx`: List/Canvas and Fit controls.
- `src/components/graph/graph-list.tsx`: default accessible results.
- `src/components/graph/graph-canvas.tsx`: bounded React Flow rendering only.
- `src/components/graph/graph-inspector.tsx`: evidence details and limitations.
- `src/components/admin/admin-app.tsx`: URL-tab orchestration and role response.
- `src/components/admin/team-access-panel.tsx`: invite/offboard.
- `src/components/admin/tools-panel.tsx`: search/catalog/permissions/enable state.
- `src/components/admin/curation-panel.tsx`: glossary and entity rules.
- `src/components/admin/usage-panel.tsx`: real personal/company totals only.
- `src/components/auth/auth-layout.tsx` and `auth-card.tsx`: shared Auth composition.
- `src/components/auth/sign-in-form.tsx`, `sign-up-form.tsx`, `forgot-password-form.tsx`, `reset-password-form.tsx`, and `invitation-accept-form.tsx`: one supported form per file.
- Route page files remain thin server/client composition boundaries; they do not duplicate page markup or data logic.

Migration rules:

- If an existing file already owns the target behavior under another path, move/rename it and update imports/tests in the same packet.
- Delete obsolete component and CSS Module files only after the new owner passes tests and a reference search shows no imports.
- Do not leave compatibility re-export files unless an external package imports them. Internal imports must be updated directly.
- Do not put multiple page applications back into a single `auth-screens.tsx` or other monolithic catch-all file.

### Exact product copy rules

- Brand: “Smart RAG.”
- Product descriptor: “Company knowledge.”
- Use “Ask,” not “Chat test bench” or “Auto chat.”
- Use “Search ready,” not internal “Hybrid Ready,” in primary user-facing status; the exact internal status may appear in details.
- Use “Graph ready,” “Graph pending,” and “Graph unavailable” only from real state.
- Generic error title: “Something went wrong.”
- Generic retry body: “The request could not be completed. Try again.”
- Permission title: “You don’t have access.”
- Not found title: “This item is unavailable.”
- Rate limit: “Too many requests. Try again in {seconds}.”
- Budget: “Question answering is paused because the usage limit was reached.”
- Service unavailable: “Question answering is temporarily unavailable.”
- Never show GAP IDs, stack traces, exception strings, database/provider names, “mock,” “fixture,” or implementation-phase language in production UI.

### Mandatory visual acceptance criteria

- The implementation must include screenshots or Playwright visual snapshots at 390px and 1280px for Sign in, Ask empty, Ask generating, Ask verifying, Ask completed with citations, Documents populated, Import source, Document detail, Tables results, Graph list, Graph canvas, and every Admin tab.
- At 390px, no page-level horizontal overflow is allowed. A labeled table/canvas region may scroll internally.
- At 1280px, content must use available width without oversized empty gutters, except readable answer text remains capped at 880px.
- All controls match the exact heights, radii, typography, colors, and states above.
- No page contains more than one visually dominant Primary button in the same immediate region.
- No permanent disabled button, decorative button, fake control, unsupported tab, duplicate panel, or empty dashboard card is visible.
- The weak implementation model must compare completed components against this specification directly; it must not answer a design question by searching GitHub, Stitch, or another design system.

## Open-source UX references

Use these only as pattern references. Do not copy code, assets, branding, or visual identity. Preserve notices if any code is deliberately adapted, although this plan expects original implementation.

- [LibreChat](https://github.com/danny-avila/LibreChat) — MIT: focused send/stop state, active generation indicators, searchable session drawer, and accessible live announcements.
- [DocsGPT](https://github.com/arc53/DocsGPT) — MIT: explicit reconnect state, bounded retry, upload stages, `aria-live`, and semantic progress.
- [AnythingLLM](https://github.com/Mintplex-Labs/anything-llm) — MIT: multi-file upload queue and document-grouped citation drawer; do not copy simulated progress.
- [RAGFlow](https://github.com/infiniflow/ragflow) — Apache-2.0: compact document status/action rows, parse logs/retry, table previews, and source evidence patterns.
- [Neo4j LLM Graph Builder](https://github.com/neo4j-labs/llm-graph-builder) — Apache-2.0: bounded graph canvas, legends, zoom-to-fit, and persistent node/property inspector.
- [Chainlit](https://github.com/Chainlit/chainlit) — Apache-2.0: minimal composer, compact settings, task status, and accessible table/data elements.
- [Hugging Face Chat UI](https://github.com/huggingface/chat-ui) — Apache-2.0: stream reattachment, abort-safe rendering, responsive drawers, and visible open/close controls.

Do not use Open WebUI, Dify, or LobeHub code because their current licenses add non-standard branding/commercial constraints. Do not use AGPL code from Khoj. Do not copy Onyx enterprise-licensed directories.
