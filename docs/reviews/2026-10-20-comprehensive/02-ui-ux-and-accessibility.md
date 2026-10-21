# UI, UX, and accessibility review

See [scope and evidence conventions](README.md). Verdict: **coherent operating console, with mobile workspace and evidence-reading weaknesses**.

## Evidence and integrity verdict

The implementation expresses a recognizable product: Ask, Documents, Tables, Graph, role-gated administration, and Account. Evidence citations have their own visual treatment. Local IBM Plex Latin/Arabic fonts, shared tokens, common controls, and restrained surfaces are appropriate for a document console. Implementation integrity passes at the product-system level; this is not a formal accessibility conformance assessment.

Inspected visual references: `docs/assets/readme/ask.png` and committed mobile Ask, desktop Documents, and desktop Graph snapshots. Current `chat-app.tsx`, `chat-rail.module.css`, `citation-drawer.tsx`, UI primitives, and tokens were checked against them. The screenshots mostly show empty/loading states, so they cannot establish the quality of populated results or every current interaction.

Three actual Chromium login checks passed. No authenticated browser review was completed. No claim of WCAG AA conformance, current signed-in screenshot accuracy, or measured Core Web Vitals is made.

## Provisional technical health score

This score rates inspected implementation evidence only. It must not be used as a release or compliance score.

- Accessibility: **2/4** — labels, skip link, focus helpers, and direction handling exist; modal candidate selection remains incomplete and signed-in assistive-technology behavior is unverified.
- Performance: **2/4** — local fonts and bounded reveal updates are good; citation previews require full-source fetch/render and no browser performance trace was collected.
- Responsive design: **2/4** — breakpoints exist, but compact Ask retains a large Sessions region above the conversation.
- Theming: **3/4** — coherent light tokens and shared components. Dark mode is not a product requirement established here; light-only design is not itself a defect.
- Implementation integrity: **3/4** — product-specific structure and truthful source origins, with partial-verification copy and source-reading limitations.

**Total: 12/20, provisional.** The uncertainty is substantial because authenticated runtime flows were not exercised.

## UI-01 — P2: compact Ask duplicates Sessions navigation and consumes conversation space

**Evidence: confirmed code and matching historical mobile fixture.** `chat-rail.module.css:229` sets compact grid rows to `minmax(8rem, 28vh) minmax(0, 1fr)` and explicitly keeps the rail displayed. `chat-app.tsx` also displays a compact Sessions button opening a sheet. `compactAsk` applies through 1,279 px.

**Impact:** a narrow screen gives a substantial fixed portion of its height to the session list even when the user is trying to read an answer or use the composer. The sheet entry duplicates a rail that remains visible. The inspected 390 px fixture makes this cost visible.

**Recommendation:** on compact layouts, use one Sessions entry and reserve the main region for conversation, progress, and composer. Keep the desktop rail and independent scrolling. Validate at 390, 768, 1,024, and 1,280 px, including the software keyboard and long answers.

**Acceptance:** no duplicate always-visible Sessions region on compact Ask; composer remains reachable and source inspection restores focus. Suggested UI command: `$impeccable adapt`.

## UI-02 — P2: PDF evidence is authentic but not yet a usable reader at small sizes

**Evidence: confirmed code.** `citation-drawer.tsx:139` renders the page as one `<img>`. `chat-transcript.module.css` gives `.citationPageImage` `width: 100%; height: auto`. The drawer has no application zoom, fit-width/actual-size switch, pan controls, selectable page text, or retry action for a failed page request.

**Impact:** a whole page reduced to the drawer width can make small labels, tables, or code hard to inspect. The supporting passage is useful, but cannot substitute for reading the original diagram/table. Browser zoom exists, but enlarges the entire console and is not an equivalent source-reader interaction.

**Recommendation:** retain the authorized single-page PNG contract; add accessible page zoom and an explicit retry, with a scrollable page viewport. Do not expose a complete PDF or a privileged storage URL just to gain reader controls. A selectable authorized text layer can be a later feature if provenance and accessibility are designed together.

**Acceptance:** a dense page/table is readable on desktop and mobile without losing panel close/navigation; the quoted passage remains available on image failure. Suggested commands: `$impeccable harden`, `$impeccable adapt`.

## UI-03 — P2: modal focus helper includes hidden/inert descendants

**Evidence: confirmed code; full user impact needs browser validation.** `ui/focus-trap.ts:40` filters only the `disabled` attribute. It does not exclude hidden ancestors, CSS-hidden elements, `inert` descendants, or `aria-disabled` widgets. The listener wraps only when focus is exactly on the selected first/last node. `Sheet` uses this helper and `aria-modal`, but does not itself make the rest of the application inert.

**Impact:** dynamic sheet contents can produce an invisible first/last candidate, making wrap behavior unreliable. Screen-reader virtual navigation and programmatic focus can also escape assumptions that a keyboard-only trap makes.

**Recommendation:** filter actual visible, focusable candidates; deliberately handle an empty modal by focusing the dialog root; manage background inertness and stacked overlays. Add a real-browser regression with hidden first/last controls and a nested panel. Do not infer conformance from the presence of `aria-modal`.

**Acceptance:** Tab/Shift+Tab, Escape, focus restoration, hidden descendants, and stacked sheets work with keyboard and a screen reader. Suggested command: `$impeccable harden`.

## UI-04 — P2: partial-answer language overstates what was verified

**Evidence: confirmed code.** `answer-surface.tsx` says “Partial answer. Verified tokens are kept.” `lib/limitations.ts` says the `verifier_skipped` path passed citation checks and that final verification timed out. Backend `verify.py` can use this family for arbitrary exceptions, restore a draft, and bypass citation persistence; see AG-04.

**Impact:** the wording can imply a level of evidence checking that did not occur. A user cannot reliably distinguish an incomplete supported answer from a draft released after an internal failure.

**Recommendation:** fix backend release semantics first. Then map separate reason codes to accurate copy: supported partial, verifier unavailable, source unavailable, and deadline exhausted. Keep technical exception names out of normal product copy.

**Acceptance:** every displayed verification claim corresponds to actual performed checks. Suggested command: `$impeccable clarify`.

## Other observations

- The library clearly states that filtering applies only to loaded documents. This is honest, but users with a large corpus still lack global name search in this surface. Treat a server-side search as a product improvement, not a hidden-button fix.
- Compact 28 px rail toggles and 36 px icon controls merit touch-target testing. A sub-44 px control is not automatically a WCAG AA failure; target-size exceptions and spacing matter.
- `prefers-reduced-motion` is handled in the answer-reveal hook. Do not replace all motion with a global duration hack without checking useful state feedback.
- Detector output contains four bounce-easing occurrences and two “broken image” matches in test fixture strings. The test-string matches are false positives for shipped UI. Easing is a low-priority style observation, not a release blocker.
- No contrast violation is asserted from screenshots alone. Existing token/contrast tests are useful; actual populated interactive states still need coverage.

## Recommended sequence

1. `$impeccable clarify`: align partial-answer copy with corrected backend semantics.
2. `$impeccable adapt`: reclaim compact Ask space and verify source-page reading.
3. `$impeccable harden`: strengthen focus behavior and source-image retry/zoom.
4. `$impeccable audit`: repeat the signed-in browser assessment after fixes.
5. `$impeccable polish`: finish spacing and motion only after functional issues pass.

These are recommendations, not edits made during this review.
