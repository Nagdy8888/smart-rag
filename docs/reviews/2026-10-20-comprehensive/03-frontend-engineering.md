# Frontend engineering review

See [scope and evidence conventions](README.md). Verdict: **buildable, substantially tested frontend with a few important correctness and test-quality boundaries**.

## Architecture and strengths

The Next.js app is primarily an authenticated client console. `src/proxy.ts` refreshes Supabase cookies and performs convenience redirects. Its comments correctly identify FastAPI authorization as the actual boundary. Shared `lib` helpers manage API classification, safe text, citation labels, answer parsing, transcript reconciliation, and source origins. Chat composition delegates stateful concerns to hooks.

The implementation has several good details:

- Model/retrieved text is rendered through React text and explicit prose/code/table components rather than arbitrary HTML.
- Citation page requests use bearer auth and explicit run/citation identifiers; object URLs are revoked on cleanup.
- Page-image failure does not intentionally remove the supporting passage.
- Answer reveal is a presentation layer over authoritative buffered text, with a 2.5-second deadline, maximum 90 publications, reduced-motion handling, and a skip action.
- The code distinguishes Company, General, and Web origins instead of implying every answer is document-grounded.
- Session, conversation restore, SSE, citation labels, and safe rendering have extensive unit coverage.

## Results actually obtained

Frontend TypeScript, ESLint, and a production build passed. The full Vitest run produced **695 passes and 2 failures** across 89 files. A focused repeat yielded **17 passes and 1 failure** across the two originally failing files.

The stable failure is the ChatApp line budget, FE-01, described in [architecture](01-architecture-and-structure.md). The other failure is a test synchronization problem candidate:

`components/core-rag-surfaces.test.tsx:358` immediately expects the asynchronous page-image failure message after waiting for passage text that is already present. In the failed run the DOM still showed “Loading page…” and retained the passage. The focused repeat passed without source changes.

**Recommendation:** await the failure-state element or the loader rejection transition directly. Preserve the assertion that the passage remains visible. Do not remove the test or classify this result as proof that the actual drawer never handles an error.

## State ownership

`ChatApp` calls `useChatQueries` twice with different run-related inputs. Query caching can deduplicate network work, so this is not proof of duplicate requests. It does make state provenance harder to follow: initial readiness/auth/conversation data comes through one hook result, while current messages, citations, and readiness also come through another.

Prefer a stable base-session/readiness query layer plus a clearly separate run-detail query layer. Before changing this, capture behavior for conversation switches, terminal events, historical citation selection, and session revocation. Refactor to make those ownership rules easier to explain, not simply to reduce hook count.

The component also mirrors `actions.loadingEarlier` into local state during render to coordinate scroll behavior. React permits certain same-component render adjustments, so this is not automatically an infinite loop. Still, the coupling should be documented or simplified when FE-01 is addressed.

## Rendering and answer correctness

The frontend's structured renderer is a worthwhile investment, but it cannot repair the backend's post-verification semantic changes, truncated native blocks, or altered paragraph/citation mapping. AG-01, AG-02, and AG-05 are backend/agent release defects whose symptoms appear in the UI.

`lib/answer-table.ts` is 939 lines and `chat/answer-surface.tsx` is 773 lines. Their size is not itself a bug, but changes need a broad rendering corpus: ordinary prose containing words like “class,” real code declarations, fenced code, stacked PDF table records, Arabic, mixed tables/prose, figures, and historical escaped text. Avoid adding single-question regex exceptions without proving that ordinary prose and existing formats still work.

## Accessibility and browser behavior

See [UI findings](02-ui-ux-and-accessibility.md) for compact layout, focus, and page reading. The three browser checks here cover login only. The existing test named “200% zoom” merely uses a small viewport and checks control visibility; actual browser zoom and text resizing require additional verification.

The signed-in Playwright helper explicitly skips when credentials or a local API are missing. That makes optional developer tests convenient, but release automation must require those journeys elsewhere; otherwise a green test command can mostly prove login and static fixtures.

## Frontend security posture

Exact-origin connection CSP, no production `unsafe-eval`, safe text handling, cookie refresh, generic error presentation, and server-derived roles are positive. Production scripts retain `unsafe-inline`; SEC-05 discusses the deliberate defense-in-depth tradeoff. The frontend must never receive Storage Admin, database, or provider credentials.

The Node audit still reports moderate/low toolchain advisories even though the high-threshold gate exits zero. Some packages are documentation/dev tooling, so there is no basis here to call all of them browser-exploitable. See SEC-04 for exposure-aware remediation.

## Recommended frontend work

1. Repair the stable architecture-budget failure without weakening the test.
2. Synchronize the timing-sensitive citation test with its actual asynchronous state.
3. Correct partial-verification copy after AG-04 is fixed.
4. Make compact Ask conversation-first and improve page reading controls.
5. Add hidden/inert focus and authenticated restore/cancellation browser coverage.
6. Measure a populated long transcript and large table in a production build before introducing virtualization or memoization changes.

No bundle-size or memory regression is claimed without a production trace. Build success confirms packaging/type integration, not authenticated runtime correctness or UX performance.
