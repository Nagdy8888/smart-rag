# Rules and commands for every packet

Read this file first in every run, then exactly one `P*.md` packet.

## Working rules

1. One packet per run. Do not start the next packet in the same run.
2. Before editing, open every file the packet lists under **Read first**
   and confirm the quoted function signatures exist. If a signature
   differs from the packet, stop and report the difference instead of
   guessing.
3. Copy code from the packet verbatim where it says **exact code**. Where
   it says **shape**, keep the names but adapt to what the file shows.
4. Every new or changed Python function, class, and method gets a
   Google-style docstring (purpose, Args, Returns, Raises, Side Effects
   when relevant). Every exported TypeScript symbol gets TSDoc.
5. Never delete or weaken an existing test to make it pass. Update the
   assertion only where the packet says so, and only in the way it says.
6. Never add `TODO`, placeholder returns, `except: pass`, or a fake
   success path.
7. Do not touch frozen JSON under
   `packages/core/src/smart_rag_core/retrieval/frozen/` or any
   `*_SHA256` constant.
8. Do not change SQL migrations unless a packet says so (none do).
9. Docs are part of the change. Each packet lists the docs to update.
   Add every new doc to `docs/README.md`.
10. At the end of the run, paste the **Done when** checklist with each
    line marked pass/fail and the command output that proves it.
11. All work happens on branch `fix/ka50-accuracy-repair` (see **Git
    workflow**). Each packet ends with one commit and one push, and the
    next packet starts only after the GitHub `PR fast` checks on that
    push are green.
12. Any live run (subset or full) is only evidence if the Compose `api`
    image was rebuilt from the current branch first (see **Docker rebuild
    before any live run**). A live run against a stale image is not
    evidence; say so instead of reporting it.

## Repo facts (verified 2026-09-22)

- Python is run with `uv run python ...` from the repo root.
- Unit tests: `uv run python -m pytest tests/unit/<file>.py -q`.
- Whole unit tier: `uv run python scripts/check.py --tier unit`.
- Lint: `uv run python scripts/check.py --tier lint` (Ruff).
- Types: `uv run python scripts/check.py --tier types` (pyright with baseline).
- Format: `uv run python -m ruff format <paths>` then
  `uv run python scripts/check.py --tier format`.
- Docs lint: `uv run python scripts/check.py --tier docs`.
- Frontend (pnpm workspace, package `smart-rag-frontend`):
  `pnpm --filter smart-rag-frontend lint`,
  `pnpm --filter smart-rag-frontend typecheck`,
  `pnpm --filter smart-rag-frontend test`.
  Or the whole tier: `uv run python scripts/check.py --tier frontend`.

### Docker rebuild before any live run

`SMART_RAG_EVAL_BASE_URL` in `.private-eval/eval-credentials.json` points at
the laptop Compose API (`http://127.0.0.1:8000`). That container runs the
code baked into the `api` image: `apps/backend/Dockerfile` copies
`packages/core/src`, `apps/agents/src`, and `apps/backend/src` at build
time. Nothing you change under `packages/` or `apps/` reaches the eval
until the image is rebuilt and the container recreated. The stack is
started with `.env.compose` plus the `docker-compose.packet8.yml` overlay
(same as `scripts/dev.ps1`); `docker compose` without `--env-file` fails
on `WORKER_SUPABASE_DB_URL`.

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -c "import importlib; checks={'P0':('smart_rag_core.query_routing.models.results','HybridBranchDiagnostics'),'P1':('smart_rag_core.retrieval.rerank','CHANNEL_HEAD_PIN'),'P2':('smart_rag_core.query_routing.constants','LIMITATION_VERIFIER_SKIPPED'),'P3':('smart_rag_core.query_answer.citations','CitationPersistResult'),'P4':('smart_rag_core.query_answer.bind','_repair_link_chunk_ids'),'P5':('smart_rag_core.sse.store','EVENT_STORE_SESSION_SQL')}; [print(k, 'present' if hasattr(importlib.import_module(m), a) and (k!='P0' or 'rerank_pool_ids' in getattr(importlib.import_module(m), a).model_fields) else 'MISSING') for k,(m,a) in checks.items()]"
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

Read the probe output honestly: every packet already merged into the
branch must print `present`; packets not yet done print `MISSING` and
that is expected. `health/ready` must contain `"query_ready": true`. The
runtime image is distroless (no shell), so only `python -c` works inside
`exec`. Frontend copy changes (P2, P3) do not affect the eval; add
`frontend` to the `up` command only when you want to see the banner text.

### KA50 live run

The 50 questions in `.private-eval/known-answer-50-v1.json` were written
from specific pages of the ingested PDF, so every expected answer is known
and page-anchored. This is the end-to-end accuracy test for the plan.
Needs `.private-eval/eval-credentials.json` and `OPERATOR_SUPABASE_DB_URL`
in `.env`, and a freshly rebuilt `api` image (previous section).

```powershell
uv run python scripts/run_company_ask.py `
  --gold .private-eval/known-answer-50-v1.json `
  --out .private-eval/ka50-summary.json `
  --credentials .private-eval/eval-credentials.json `
  --progress .private-eval/ka50-progress.json `
  --answers-out .private-eval/ka50-answers.json `
  --stage-export .private-eval/ka50-stages.json `
  --verbose
```

Run notes:

- Resume rule: if `--answers-out` exists, only missing question ids run.
  To re-run everything, move the old `ka50-answers.json`,
  `ka50-progress.json`, `ka50-stages.json`, `ka50-summary.json` into
  `.private-eval/runs/<date>/` first.
- Subset run: write a filtered copy of the gold JSON (same schema, fewer
  items) and pass it as `--gold`. There is no `--ids` flag.
- One question takes about 60 s live. Ten questions is about 12 minutes.

## Git workflow

Repo facts (verified 2026-09-22): remote `origin` is
`https://github.com/Nagdy8888/Demo_Project_3.git`, default branch `main`,
`gh` 2.89 is logged in as `Nagdy8888`, `main` has no branch protection
(so **you** enforce green checks; GitHub will not), and the last PR
(`#16`) was merged with a merge commit. The `PR fast` workflow
(`.github/workflows/pr-fast.yml`) runs on every push to a PR branch:
`preflight`, `format-lint`, `types`, `unit`, `contract`,
`docs-frontend`, `openapi-migrations` (about 11 minutes). `Main`
(`.github/workflows/main.yml`) runs `unit`, `contract`, `compose` on
every push to `main`.

`.private-eval/`, `.env`, and `.env.*` are gitignored. Never force-add
them. `.cursor/plans/` **is** tracked; the plan files are committed with
P0.

### Once, before P0

```powershell
git checkout main
git pull --ff-only origin main
git checkout -b fix/ka50-accuracy-repair
git add .cursor/plans/ka50_accuracy_repair_7e21c4d9.plan.md .cursor/plans/ka50-accuracy-repair
git commit -m "docs(plan): KA50 accuracy repair plan P0-P8"
git push -u origin fix/ka50-accuracy-repair
gh pr create --draft --base main --head fix/ka50-accuracy-repair --title "fix: KA50 accuracy repair (P0-P8)" --body "Implements .cursor/plans/ka50_accuracy_repair_7e21c4d9.plan.md. One commit per packet. Acceptance: strict_pass >= 32/50 on the known-answer-50 set after rebuilding the api image. Evidence doc added in P7."
```

If the branch already exists (a previous run created it), skip the
`checkout -b` and `pr create` lines: `git checkout fix/ka50-accuracy-repair`
then `git pull --ff-only`.

### At the end of every packet (P0-P7)

```powershell
git status --short
```

The list must contain only files the packet touched. If `.private-eval/`
or `.env*` appear, they are untracked noise - do not add them. Then:

```powershell
git add <every changed/added path from the packet, one by one>
git commit -m "<commit message given at the end of the packet>"
git push
gh pr checks --watch --fail-fast
```

`gh pr checks --watch --fail-fast` exits 0 only when every `PR fast` job
is green. If it exits non-zero: open the failing job with
`gh run view --log-failed` (use the run id it prints), fix the cause on
this branch, commit as `fix(ci): <what>` and push again. Never use
`git add -A`, `git add .`, `--no-verify`, `--force`, or `--admin`. Never
start the next packet on red checks.

## Key paths

| Concern | Path |
| --- | --- |
| Profile selection | `packages/core/src/smart_rag_core/retrieval/source_scope.py` |
| Frozen profile loader | `packages/core/src/smart_rag_core/retrieval/frozen_profile.py` |
| Rerank pool | `packages/core/src/smart_rag_core/retrieval/rerank.py` |
| Context selection | `packages/core/src/smart_rag_core/retrieval/context.py` |
| Hybrid retriever | `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py` |
| Hybrid diagnostics model | `packages/core/src/smart_rag_core/query_routing/models/results.py` |
| Diagnostics builder | `packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py` |
| Verify node | `apps/agents/src/smart_rag_agents/query/nodes/verify.py` |
| Citation persistence | `packages/core/src/smart_rag_core/query_answer/citations.py` |
| Citation binder | `packages/core/src/smart_rag_core/query_answer/bind.py` |
| Paragraph contract | `packages/core/src/smart_rag_core/query_answer/paragraphs.py` |
| Verification model | `packages/core/src/smart_rag_core/query_answer/models.py` |
| SSE verified mapping | `apps/backend/src/smart_rag_api/services/sse/mapping/verified.py` |
| SSE limitations | `apps/backend/src/smart_rag_api/services/sse/mapping/limitations.py` |
| SSE mapper | `apps/backend/src/smart_rag_api/services/sse/mapping/mapper.py` |
| SSE event store | `packages/core/src/smart_rag_core/sse/store.py` |
| Frontend limitation copy | `apps/frontend/src/lib/limitations.ts` |
| Eval runner | `scripts/run_company_ask.py` |
| Eval stage export | `scripts/eval_ask_stage_export.py` |
| Scorer | `packages/core/src/smart_rag_core/evaluation/dual_metric.py` |

## Reporting template (paste at the end of each run)

```text
Packet: P<n>
Files changed: <list>
Tests added/updated: <list>
Commands run and exit codes:
  uv run python -m pytest tests/unit/<...> -q  -> exit 0, N passed
  uv run python scripts/check.py --tier lint          -> exit 0
  uv run python scripts/check.py --tier types         -> exit 0
Done when:
  [pass|fail] <line 1>
  ...
Commit: <sha> "<message>" pushed to fix/ka50-accuracy-repair
PR fast checks: green | red (<failing job>)
Image rebuilt for live proof: yes (<probe output>) | no live run in this packet
Deviations from the packet: <none | describe>
Unverified: <what could not be run and why>
```
