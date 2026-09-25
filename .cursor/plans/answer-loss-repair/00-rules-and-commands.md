# Rules and commands for every packet

Read this file first in every run, then **exactly one** `A*.md` packet.
Do not read sibling packets. Do not read the big Hybrid/Graph RAG plan.
Everything you need is in this file and your packet.

The plan also runs latency packets L0-L4 (after A2, before A3). For an
`L*` packet, read `../query-latency-repair/00-rules-and-commands.md`
instead of this file, then that one packet. The order is in the plan
index `.cursor/plans/answer_loss_repair_9c24e1a0.plan.md`.

Decision record for the whole plan:
[`docs/adr/ADR-retrieved-answer-loss-repair.md`](../../../docs/adr/ADR-retrieved-answer-loss-repair.md).
Measured evidence:
[`docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md`](../../../docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md).
Read both once before your first packet. Do not change them unless your
packet says so.

## Working rules

1. One packet per run. Do not start the next packet in the same run.
2. Before editing, open every file the packet lists under **Read first**
   and confirm each quoted signature and line exists. Line numbers may
   drift by a few lines; the function name and body must match. If a
   signature or body differs from what the packet quotes, **stop** and
   report the difference instead of guessing.
3. Where the packet says **exact code**, copy it verbatim. Where it says
   **shape**, keep every name the packet gives and adapt only the
   surrounding glue to what the file shows.
4. Every new or changed Python module, class, function, and method gets a
   Google-style docstring (purpose, `Args`, `Returns`, `Raises`,
   `Side Effects` when relevant). Every LangGraph node docstring also
   lists state inputs/outputs, persistence writes, model calls, budget or
   deadline behavior, and the failure route. Every exported TypeScript
   symbol gets TSDoc.
5. Never delete or weaken an existing test to make it pass. Change an
   existing assertion only where the packet says so, in the way it says.
6. Never add `TODO`, placeholder returns, `except: pass`, swallowed
   errors, or a fake success path.
7. Never edit an existing frozen JSON file under
   `packages/core/src/smart_rag_core/retrieval/frozen/`, any existing
   `*_SHA256` value for an old prompt or profile, or any existing prompt
   `.md` file (`answer_v1.md`, `answer_v2.md`, `answer_v3.md`,
   `rerank_v1.md`, `verifier_v1.md`, `verifier_v2.md`, ...). New versions
   are new files.
8. No SQL migrations in this plan. If you think one is needed, stop and
   ask.
9. Docs are part of the change. Each packet lists the docs to update.
   Every new doc gets a row in `docs/README.md`.
10. Never put private questions, gold phrases, answer text, or raw PDF
    text into a tracked file. `.private-eval/`, `.env`, and `.env.*` are
    gitignored; keep it that way.
11. At the end of the run, paste the **Reporting template** below with
    every **Done when** line marked `pass` or `fail`, plus the command
    output that proves it.
12. A live run (subset or full) counts as evidence only if the Compose
    `api` image was rebuilt from the current branch first and the probe
    printed `present` for the packet (see **Docker rebuild**). A run
    against a stale image is not evidence; say so.
13. If a command fails and the fix is not obvious from the error, stop
    and report the full error. Do not try random changes.
14. The unseen set (`.private-eval/unseen50-v1.json`, written and sealed
    in A0) is for A0's baseline and A9's final score only. Packets A1-A8
    must not run it, read its questions, or tune anything on it. Tune
    and debug only on `answer50-v1.json` subsets.

## Repo facts (verified 2026-09-24)

- OS is Windows; the shell is PowerShell. Run commands from the repo root
  `c:\Nagdy\Mustafa\Work\Upwork\Demo_Project_3`.
- Python: `uv run python ...`. Private scripts under `.private-eval/`
  also work with `.venv\Scripts\python.exe` (the system Python lacks
  `psycopg`).
- Set `$env:PYTHONIOENCODING = "utf-8"` before any script that prints PDF
  text; the book uses U+2010 hyphens and cp1252 cannot print them.
- One unit test file: `uv run python -m pytest tests/unit/<file>.py -q`.
- Whole unit tier: `uv run python scripts/check.py --tier unit`.
- Contract tier: `uv run python scripts/check.py --tier contract`.
- Lint (Ruff): `uv run python scripts/check.py --tier lint`.
- Types (pyright with baseline): `uv run python scripts/check.py --tier types`.
- Format: `uv run python -m ruff format <paths>` then
  `uv run python scripts/check.py --tier format`.
- Docs (markdownlint, links, Mermaid render): `uv run python scripts/check.py --tier docs`.
  It takes about 6 minutes; run it once near the end of the packet.
- Everything fast at once: `uv run python scripts/check.py --tier fast`.
- Frontend (only if a packet touches `apps/frontend`):
  `pnpm --filter smart-rag-frontend lint`,
  `pnpm --filter smart-rag-frontend typecheck`,
  `pnpm --filter smart-rag-frontend test`.

## Private files you will use

| File | What it is |
| --- | --- |
| `.private-eval/eval-credentials.json` | Eval login and `base_url` (`http://127.0.0.1:8000`) |
| `.private-eval/answer50-v1.json` | The 50 answer-only questions that were diagnosed |
| `.private-eval/answer50-answers.json` | Baseline answers + stage IDs for those 50 (2026-09-24) |
| `.private-eval/answer50-summary.json` | Baseline scores for those 50 |
| `.private-eval/answer50_stage_trace.py` | Prints per-stage rank of the fact chunk |
| `.private-eval/answer50_checkpoint_dump.py` | Prints generated vs released fact per question |
| `.private-eval/latency_probe.py` | Prints per-node timings from `app.run_events` |
| `.private-eval/used-pages.txt` | Pages used by the two earlier 50-question sets |

`OPERATOR_SUPABASE_DB_URL` must be present in `.env` or `.env.compose` for
the private diagnostics. Never print it.

## Docker rebuild before any live run

The eval calls the laptop Compose API on `http://127.0.0.1:8000`. That
container runs the code baked into the `api` image. Nothing you change
under `packages/` or `apps/` reaches the eval until you rebuild.

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

`health/ready` must contain `"query_ready": true`. Then run the probe.
The image is distroless (no shell), so only `python -c` works:

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -c "import importlib; checks={'A1':('smart_rag_core.query_answer.claims','claims_to_answer_payload'),'A2':('smart_rag_core.retrieval.rerank','RerankPayloadError'),'A3':('smart_rag_core.retrieval.rerank_versions','RERANK_LABEL_PREFIX'),'A4':('smart_rag_core.retrieval.frozen_profile','LONG_DOCUMENT_V3_PROFILE_ID'),'A5':('smart_rag_core.retrieval.profiles','CHANNEL_PHASE_RESERVE_SECONDS'),'A6':('smart_rag_core.ingestion.parser.helpers','LINE_END_HYPHENS'),'A7':('smart_rag_core.ingestion.chunking.navigation','is_navigation_chunk')}; [print(k, 'present' if hasattr(importlib.import_module(m), a) else 'MISSING') for k,(m,a) in checks.items()]"
```

Read it honestly: every packet already committed on the branch must print
`present`; later packets print `MISSING`, which is expected. If a module
import fails with `ModuleNotFoundError`, that packet is `MISSING`; to see
the others, run the probe once per packet with only that entry.

## Live eval commands

One question takes about 50 to 60 s live. Ten questions take about 10
minutes; 50 take about 50 minutes.

Full answer-only run (use a fresh output folder per run; the runner
resumes from `--answers-out` if it already exists):

```powershell
New-Item -ItemType Directory -Force .private-eval/runs/<run-name> | Out-Null
uv run python scripts/run_company_ask.py `
  --gold .private-eval/answer50-v1.json `
  --out .private-eval/runs/<run-name>/summary.json `
  --credentials .private-eval/eval-credentials.json `
  --progress .private-eval/runs/<run-name>/progress.json `
  --answers-out .private-eval/runs/<run-name>/answers.json `
  --stage-export .private-eval/runs/<run-name>/stages.json `
  --verbose
```

Subset run: there is no `--ids` flag. Write a filtered copy of the gold
JSON (same schema, fewer items) into the run folder and pass it as
`--gold`. Do **not** use `ConvertTo-Json | Set-Content -Encoding utf8`:
Windows PowerShell 5.1 writes a byte-order mark the runner rejects and
turns a one-item list into a bare object. Use `gold_subset.py`:

```powershell
.venv\Scripts\python.exe .private-eval/gold_subset.py --gold .private-eval/answer50-v1.json --ids a02,a09,a10 --out .private-eval/runs/<run-name>/gold.json
```

It must print `questions=<number of IDs>`. If
`.private-eval/gold_subset.py` does not exist yet, create it with exactly
this code (A9 carries the same code; the file is gitignored):

```python
"""Write a filtered copy of a private gold file for a subset run.

Private helper for packet A9 of the answer-loss repair plan. It replaces
the PowerShell ``ConvertTo-Json | Set-Content -Encoding utf8`` recipe, which
on Windows PowerShell 5.1 writes a UTF-8 byte-order mark (the runner's JSON
loader rejects it) and turns a one-item list into a bare object. This script
writes a JSON array in UTF-8 without a BOM and keeps the input item order.

Example:
    ``.venv/Scripts/python.exe .private-eval/gold_subset.py
    --gold .private-eval/known-answer-smoke-v1.json --ids ka-12
    --out .private-eval/runs/a9-negative/gold.json``
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    """Filter the gold file by id and write the subset.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 on success, 1 when an id is unknown.

    Raises:
        SystemExit: If ``--out`` is outside ``.private-eval``.
    """

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--ids", required=True, help="comma-separated question ids")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if ".private-eval" not in args.out.resolve().parts:
        raise SystemExit(f"refusing to write outside .private-eval: {args.out}")
    wanted = [part.strip() for part in args.ids.split(",") if part.strip()]
    items = json.loads(args.gold.read_text(encoding="utf-8"))
    known = {item["id"] for item in items}
    unknown = [qid for qid in wanted if qid not in known]
    if unknown:
        print(f"ERROR unknown ids: {','.join(unknown)}")
        return 1
    subset = [item for item in items if item["id"] in set(wanted)]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(subset, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"wrote {args.out} questions={len(subset)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

## Git workflow

Remote `origin` is `https://github.com/Nagdy8888/Demo_Project_3.git`,
default branch `main`, and `gh` is logged in. `main` has no branch
protection, so **you** enforce green checks. The `PR fast` workflow runs
on every push to a PR branch (about 11 minutes).

### Once, at the start of A0

The previous repair is
[PR #17](https://github.com/Nagdy8888/smart-rag/pull/17) on branch
`fix/ka50-accuracy-repair`; it was merged on 2026-09-24 (merge commit
`148c44f`). Confirm it is still merged:

```powershell
gh pr view 17 --json state,mergedAt
```

- If `state` is `MERGED`: cut the new branch from `main`.

  ```powershell
  git stash push --include-untracked -m "answer-loss-plan-docs" -- .cursor/plans/answer_loss_repair_9c24e1a0.plan.md .cursor/plans/answer-loss-repair .cursor/plans/query_latency_repair_3f9c2a61.plan.md .cursor/plans/query-latency-repair docs
  git checkout main
  git pull --ff-only origin main
  git checkout -b fix/answer-loss-repair
  git stash pop
  ```

- If `state` is `OPEN`: **stop and ask the user** whether to ship PR #17
  first or to stack this branch on it. If the user says stack:

  ```powershell
  git checkout fix/ka50-accuracy-repair
  git pull --ff-only origin fix/ka50-accuracy-repair
  git checkout -b fix/answer-loss-repair
  ```

  and use `--base fix/ka50-accuracy-repair` in `gh pr create` below.

Then commit the plan and the docs written before A0 (list the paths one
by one; never `git add -A` or `git add .`):

```powershell
git add .cursor/plans/answer_loss_repair_9c24e1a0.plan.md .cursor/plans/answer-loss-repair
git add .cursor/plans/query_latency_repair_3f9c2a61.plan.md .cursor/plans/query-latency-repair
git add docs/adr/ADR-retrieved-answer-loss-repair.md docs/adr/README.md docs/README.md
git add docs/evaluation/ANSWER_ONLY_50_2026-09-24.md docs/evaluation/ANSWER_ONLY_50_ROOT_CAUSES_2026-09-24.md
git add docs/evaluation/FRESH_KNOWN_ANSWER_50_2026-09-23.md docs/evaluation/KNOWN_ANSWER_50_REPAIR_EVIDENCE_2026-09-22.md
git commit -m "docs(plan): answer-loss repair ADR, root causes, and plan A0-A10"
git push -u origin fix/answer-loss-repair
gh pr create --draft --base main --head fix/answer-loss-repair --title "fix: answer-loss and query-latency repair (A0-A10, L0-L4)" --body "Implements .cursor/plans/answer_loss_repair_9c24e1a0.plan.md (which includes latency packets L0-L4 from .cursor/plans/query-latency-repair/) and docs/adr/ADR-retrieved-answer-loss-repair.md. One commit per packet. Acceptance: at least 40/50 right on an unseen answer-only set and on the diagnosed set after rebuilding the api image. Evidence doc added in A9."
```

If the branch already exists (a previous run created it):
`git checkout fix/answer-loss-repair` then `git pull --ff-only`.

### At the end of every code packet (A1 to A9)

```powershell
git status --short
```

The list must contain only files the packet touched. If `.private-eval/`
or `.env*` appear, they are untracked noise; do not add them. Then:

```powershell
git add <every changed/added path from the packet, one by one>
git commit -m "<commit message given at the end of the packet>"
git push
gh pr checks --watch --fail-fast
```

`gh pr checks --watch --fail-fast` exits 0 only when every `PR fast` job
is green. If it exits non-zero, open the failing job with
`gh run view <run-id> --log-failed`, fix the cause on this branch, commit
as `fix(ci): <what>`, and push again. Never use `git add -A`,
`git add .`, `--no-verify`, `--force`, or `--admin`. Never start the next
packet on red checks.

## Key paths

| Concern | Path |
| --- | --- |
| Answer prompt pin (agents) | `apps/agents/src/smart_rag_agents/prompts/__init__.py` |
| Prompt registry | `apps/agents/src/smart_rag_agents/prompts/registry.py` |
| Prompt changelog | `apps/agents/src/smart_rag_agents/prompts/CHANGELOG.md` |
| Answer/verifier version pins (core) | `packages/core/src/smart_rag_core/query_answer/versions.py` |
| Answer/verifier JSON schemas | `packages/core/src/smart_rag_core/query_answer/schemas.py` |
| Answer payload models | `packages/core/src/smart_rag_core/query_answer/models.py` |
| Binder repairs | `packages/core/src/smart_rag_core/query_answer/bind.py` |
| Paragraph contract | `packages/core/src/smart_rag_core/query_answer/paragraphs.py` |
| Deterministic check | `packages/core/src/smart_rag_core/query_answer/deterministic.py` |
| Claims-only release | `packages/core/src/smart_rag_core/query_answer/release.py` |
| OpenAI answer/verifier calls | `packages/core/src/smart_rag_core/gateways/openai_answer.py` |
| Answer gateway (agents) | `apps/agents/src/smart_rag_agents/query/gateway/answer.py` |
| Generate node | `apps/agents/src/smart_rag_agents/query/nodes/answer.py` |
| Verify node | `apps/agents/src/smart_rag_agents/query/nodes/verify.py` |
| Hybrid retriever | `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py` |
| Context selection and rerank gate | `packages/core/src/smart_rag_core/retrieval/context.py` |
| Rerank pool, schema, validation, pins | `packages/core/src/smart_rag_core/retrieval/rerank.py` |
| Reranker wrapper | `packages/core/src/smart_rag_core/retrieval/reranker.py` |
| OpenAI rerank call | `packages/core/src/smart_rag_core/gateways/openai_rerank.py` |
| Rerank prompt pin | `packages/core/src/smart_rag_core/retrieval/rerank_versions.py` |
| Retrieval constants | `packages/core/src/smart_rag_core/retrieval/profiles.py` |
| Frozen profile loader | `packages/core/src/smart_rag_core/retrieval/frozen_profile.py` |
| Profile selection | `packages/core/src/smart_rag_core/retrieval/source_scope.py` |
| Hybrid diagnostics model | `packages/core/src/smart_rag_core/query_routing/models/results.py` |
| Hybrid branch and diagnostics builder | `packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py` |
| PDF line joins | `packages/core/src/smart_rag_core/ingestion/parser/helpers.py` |
| PDF parser version | `packages/core/src/smart_rag_core/ingestion/parser/limits.py` |
| Chunk model and dedup | `packages/core/src/smart_rag_core/ingestion/chunking/types.py`, `dedup.py` |
| Eval runner | `scripts/run_company_ask.py` |
| Eval stage export | `scripts/eval_ask_stage_export.py` |
| Scorer | `packages/core/src/smart_rag_core/evaluation/dual_metric.py` |

## Reporting template (paste at the end of each run)

```text
Packet: A<n>
Files changed: <list>
Tests added/updated: <list>
Commands run and exit codes:
  uv run python -m pytest tests/unit/<...> -q  -> exit 0, N passed
  uv run python scripts/check.py --tier lint          -> exit 0
  uv run python scripts/check.py --tier types         -> exit 0
Done when:
  [pass|fail] <line 1>
  ...
Commit: <sha> "<message>" pushed to fix/answer-loss-repair
PR fast checks: green | red (<failing job>)
Image rebuilt for live proof: yes (<probe output>) | no live run in this packet
Deviations from the packet: <none | describe>
Unverified: <what could not be run and why>
```
