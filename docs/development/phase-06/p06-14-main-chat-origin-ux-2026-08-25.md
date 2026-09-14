# P06-14 — Main chat origin UX (2026-08-25)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Requirement: render additive `answer_origin` on the Ask surface without
inferring origin from Hybrid/Combined/NoRetrieval route pills, and hide
citation chips except for `company_documents` or a missing (legacy)
origin.

Labels:

| Origin | Label | Citations |
| --- | --- | --- |
| `general_knowledge` | General knowledge | hidden |
| `company_documents` | Company documents | shown |
| `user_supplied_text` | Your text | hidden |
| `deterministic` | Assistant | hidden |
| `ambiguous` | Needs clarification | hidden; `LimitationCallout` with exact mixed-scope copy |
| `null` / omitted | no origin badge | shown (legacy) |
| unknown / XSS string | isolated text | hidden |

Clarification copy (exact): “This question mixes general knowledge and
company documents. Ask one general question or one document question so
the answer source stays clear.”

Empty-state title (exact): “Ask a general question, or ask about your
company documents for a cited answer.”

Auth, reconnect, cancellation, idempotency, verified-final token
holding, and source-drawer authorization were not changed. Origin is
never derived from `route_family`.

Playwright Ask journey: **skipped**. `apps/frontend/playwright.config.ts`
requires local GoTrue at `127.0.0.1:54321` and API at `:8000`. Those
processes were not running for this packet, and local Supabase is a
labelled destructive fixture rather than the hosted operator path.

Verification:

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend test` | 0 (298 passed / 44 files) |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend typecheck` | 0 |
| `pnpm --filter smart-rag-frontend build` | 0 (Next.js 16.3.0) |

Rollback: remove `answer-origin.ts`, origin fields on `ChatViewState` /
`AnswerSurface`, and restore the previous empty-state title. Leave SSE
major version `1`.

Handoff to P06-15: run deterministic plus live gates, inspect LangSmith
or mark blocked, and update routing/budget/SSE/Studio docs.

## 2026-09-13 close-out (resume after P06-36)

Wrapper Packet 14 stayed unchecked. Ask empty-state copy had drifted back
to “Ask your company knowledge”. Restored the packet title and a body that
does not claim every answer is cited.

Also repaired leftover hosted-eval frontend gates that blocked this
close-out: `createPdfEvalCase` parser null counts in `api.test.ts`, and
ChatApp/api barrel physical-line budgets (`toSaveToQuizPopoverProps`).

2026-09-13 commands:

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend test` | 0 (555 passed / 79 files) |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend typecheck` | 0 |
| `pnpm --filter smart-rag-frontend build` | 0 (Next.js 16.3.3) |

Playwright Ask journey: **skipped**. Config still targets local GoTrue
`:54321` and API `:8000`. Those processes were not started for this
close-out.

Rollback: restore the previous empty-state title; leave SSE major
version `1`.
