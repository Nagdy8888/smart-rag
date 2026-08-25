---
title: Admin and auth screen specification
owner: engineering-lead
status: draft
last-reviewed: 2026-08-25
audience: frontend, security
packet: P08-19
---

# Admin and auth screens

P08-19 ships these routes on `/login` family pages, `/admin` tabs, and `/account`. Visual values follow [ADR-ink-indigo-visual-refresh.md](../adr/ADR-ink-indigo-visual-refresh.md).

## Screen specifications

### Auth component and page specification

#### `AuthLayout`

- Two columns at `>=1024px` (45% brand / 55% form). Single centered column below.
- Brand panel: `--gradient-brand`, white content, 48px padding, 40px white logo tile, “Smart RAG” hero scale, one line exactly “Grounded answers from your company's knowledge.”
- Form column: `--color-bg`, card max-width 420px, `--radius-card`, `--shadow-1`, 32px padding, title 28/36 Inter Display.
- Skip link is visually hidden until keyboard-focused.
- Successful sign-in calls `router.replace("/")` and `router.refresh()`. Sign-in button uses `pending` / `pendingLabel="Signing in…"`.

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

### Admin component specification

#### Admin frame

- Topbar title “Admin”. No trailing period.
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

### Exact product copy rules

- Brand: “Smart RAG.”
- Product descriptor: “Grounded answers from your company's knowledge.”
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
