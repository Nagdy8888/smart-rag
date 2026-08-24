# Workspace screens

Canonical values are copied from [.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-visual-contract.md](../../.cursor/plans/hybrid-graph-rag/08-phase-frontend-integration/00-visual-contract.md). Do not reinterpret them.

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
- Do not show a streaming caret or typewriter animation. Show the real Generating/Verifying progress state, then insert verified final answer text without artificial delay.
- Partial/cancelled/error retains existing text and adds a StatusBanner below.
- Footer order: citations, feedback, then “Run details” disclosure.

#### `RunProgress`

- Compact horizontal/vertical step list using real status events.
- Known stage labels map to: “Preparing,” “Retrieving,” “Generating,” “Verifying.”
- Unknown stage renders safe neutral exact stage text in details, not as a new primary phase.
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
