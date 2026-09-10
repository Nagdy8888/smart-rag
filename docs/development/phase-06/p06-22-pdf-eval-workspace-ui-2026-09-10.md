# P06-22 — PDF eval workspace UI (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Admin Evaluation workspace for review, approval, and manual AI comparison.
The tab is capability-gated from `/api/meta`. Expected answers stay collapsed
until Reveal after a terminal run. Holdout has no Run control.

Requirement: owner/admin evaluation GET is the authorization gate; hidden
nav is not authorization. Reuse authenticated admission/SSE/citations.

Files:

- [`apps/frontend/src/components/evaluation/`](../../../apps/frontend/src/components/evaluation/)
- [`apps/frontend/src/lib/api/pdf-eval.ts`](../../../apps/frontend/src/lib/api/pdf-eval.ts)
- [`apps/frontend/src/lib/eval-workspace.ts`](../../../apps/frontend/src/lib/eval-workspace.ts)
- Additive admin tab visibility, action inventory, Playwright member assertion
- [`docs/frontend/ADMINISTRATION.md`](../../frontend/ADMINISTRATION.md)
- [`docs/evaluation/PDF_EVAL_WORKSPACE.md`](../../evaluation/PDF_EVAL_WORKSPACE.md)

Verification:

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend typecheck` | 0 |
| `pnpm --filter smart-rag-frontend test -- src/components/evaluation/evaluation-panel.test.tsx src/lib/eval-workspace.test.ts src/lib/shell-navigation.test.ts src/components/administration-surfaces.test.tsx` | 0 (25 tests) |
| `pnpm --filter smart-rag-frontend build` | 0 |

Proven: Evaluation tab hidden without capability; member/admin surfaces omit
the tab in Vitest; editor remounts on revision instead of setState-in-effect;
expected answer is not editable into the AI request from local state.

Unverified: Playwright live-member `/admin` run (needs live auth fixture).
Browser walkthrough of compare-run against a mounted workspace.

Rollback: hide the tab by leaving `pdf_eval_workspace` false in `/api/meta`.

Handoff: Packet 23 owns conservative PDF heading extraction.
