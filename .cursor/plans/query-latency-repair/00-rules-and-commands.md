# Rules and commands for every latency packet

Read this file first in every run, then exactly one `L*.md` packet.

## Working rules

1. One packet per run. Do not start the next packet in the same run.
2. Before editing, open every file the packet lists under **Read first**
   and confirm the quoted function signatures and constants exist. If one
   differs from the packet, stop and report the difference instead of
   guessing.
3. Copy code from the packet verbatim. See **How to apply an edit**. Do
   not adapt, reorder, or "improve" packet code.
4. Every new or changed Python module, class, function, and method gets a
   Google-style docstring (purpose, Args, Returns, Raises, Side Effects,
   and timeouts/retries when relevant). Every exported TypeScript symbol
   gets TSDoc.
5. Never delete or weaken an existing test to make it pass. Update an
   assertion only where the packet says so, and only in the way it says.
6. Never add `TODO`, placeholder returns, `except: pass`, or a fake
   success path. Timing code must never change control flow.
7. Do not touch frozen JSON under
   `packages/core/src/smart_rag_core/retrieval/frozen/` or any `*_SHA256`
   constant, except `RERANK_PROMPT_SHA256` in L5.
8. Do not change SQL migrations. No packet needs one.
9. Docs are part of the change. Each packet lists the docs to update. Add
   every new doc to `docs/README.md`.
10. **Combined plan.** These packets run inside
    `.cursor/plans/answer_loss_repair_9c24e1a0.plan.md`, which sets the
    order (A0, A1, A2, L0, L1, L2, L3, L4, A3, ...). Only L0-L4 are part of
    it. **L5 is dropped** (answer-loss packet A3 ships `rerank_v2`
    instead); **L6 and L7 are not written and not part of this plan**.
    Never start L5, L6, or L7. L8 and L9 are replaced by answer-loss
    packets A9 and A10.
11. At the end of the run, paste the **Done when** checklist with each line
    marked pass/fail, the command output that proves it, and the
    before/after timing table from `eval_latency_report.py compare`.
12. All work happens on branch `fix/answer-loss-repair`, created by
    answer-loss packet A0 (see **Git workflow**). Each packet ends with one commit and one push, and the
    next packet starts only after `PR fast` on that push is green.
13. A timing run is evidence only if the Compose `api` image was rebuilt
    from the current branch first and the probe prints the packet as
    `present`. A run against a stale image is not evidence; say so.
14. If `git status --short` shows pre-existing changes in a file the packet
    must edit (for example `docs/README.md`), stop and ask the user to
    commit or stash them first. Never commit the user's lines inside a
    packet commit.

## How to apply an edit

Each edit starts with a line `File: \`<path>\``. All blocks below it
apply to that file until the next `File:` line. The blocks are:

- `Full contents:` followed by one code block: write the file with
  exactly that text (create it, or replace the whole file).
- `Find (exactly once):` then `Replace with:`: the Find text must appear
  exactly once in the file. Replace it with the second block. If it
  appears zero times or more than once, stop and report; do not guess.
- `Append to the end of the file:`: add the block after the last line,
  with one blank line before it.

After all edits, run `uv run python -m ruff format <changed paths>` and
`uv run python -m ruff check --select I --fix <changed paths>`. If they
change a line you copied from the packet, keep their version and report
it under **Deviations**. Line endings (CRLF or LF) do not matter; Git
normalizes them.

## Repo facts (verified 2026-09-24)

- Python is run with `uv run python ...` from the repo root.
- Unit tests: `uv run python -m pytest tests/unit/<file>.py`. The pytest
  config already adds `-q`; the `-q` in commands below is harmless.
- `rg` exits with code 1 when it finds nothing. For a "must find
  nothing" check, exit code 1 with no output is the pass.
- Whole unit tier: `uv run python scripts/check.py --tier unit`.
- Lint: `uv run python scripts/check.py --tier lint` (Ruff).
- Types: `uv run python scripts/check.py --tier types` (pyright with baseline).
- Format: `uv run python -m ruff format <paths>` then
  `uv run python scripts/check.py --tier format`.
- Docs lint: `uv run python scripts/check.py --tier docs`.
- Contract tests that need a database: `uv run python -m pytest tests/contract -k <name> -q`
  (they skip without a database URL; a skip is **not** a pass for a packet
  that names a contract test as proof).
- Contract tier: `uv run python scripts/check.py --tier contract`. If only
  `tests/contract/test_clamav_scan.py` fails with "signature databases
  older than 1 day", that is the local virus database, not the packet.
  Refresh it with
  `docker compose --env-file .env.compose -f docker-compose.yml exec clamav freshclam`
  and run the tier again. If that command fails (for example, the
  database is locked), run
  `docker compose --env-file .env.compose -f docker-compose.yml restart clamav`;
  the container runs `freshclam` when it starts. If the test still fails,
  report it as an environment failure; do not change the test.
- Pinned versions: `psycopg[binary]==3.3.3`, `psycopg-pool` 3.3.1 (in
  `uv.lock`, pulled in by `langgraph-checkpoint-postgres==3.1.2`),
  `langgraph==1.2.11`, `openai==2.26.0`.
- Measured network facts: container to Supabase round trip 85-95 ms; a new
  connection about 500 ms; the API DSN uses the Supavisor transaction
  pooler (port 6543); checkpointer, operator, and LightRAG DSNs use 5432.

### Docker rebuild before any live run

`SMART_RAG_EVAL_BASE_URL` in `.private-eval/eval-credentials.json` points at
the laptop Compose API (`http://127.0.0.1:8000`). That container runs the
code baked into the `api` image (`apps/backend/Dockerfile` copies
`packages/core/src`, `apps/agents/src`, and `apps/backend/src`). Nothing
under `packages/` or `apps/` reaches the eval until the image is rebuilt.

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
Get-Content scripts/probe_latency_image.py -Raw | docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

`scripts/probe_latency_image.py` is added in L0. It prints one line per
packet (`L0 present`, `L1 MISSING`, ...) plus the active rerank prompt
version and pool sizes. Every packet already committed must print
`present`; later packets print `MISSING`, which is expected. In the
combined plan, `L5` prints `present` only after answer-loss A3 ships
`rerank_v2`, and `L6` and `L7` always print `MISSING`; both are expected. `health/ready`
must contain `"query_ready": true`. The runtime image is distroless (no
shell), so the probe is piped to `python -` over stdin.

### The latency-12 subset

A fixed 12-question subset of `.private-eval/fresh50-v1.json`, chosen in
L0 to cover the four deadline runs and a spread of stage timings:
`f03 f14 f15 f16 f23 f24 f33 f39 f41 f46 f47 f49`. It is written once in L0:

```powershell
uv run python scripts/eval_latency_report.py subset --gold .private-eval/fresh50-v1.json --ids f03,f14,f15,f16,f23,f24,f33,f39,f41,f46,f47,f49 --out .private-eval/latency12-v1.json
```

### Timing run (before and after every code packet)

Replace `<tag>` with the packet and side, for example `L1-after`.

```powershell
New-Item -ItemType Directory -Force .private-eval/runs/<tag> | Out-Null
uv run python scripts/run_company_ask.py `
  --gold .private-eval/latency12-v1.json `
  --out .private-eval/runs/<tag>/summary.json `
  --credentials .private-eval/eval-credentials.json `
  --progress .private-eval/runs/<tag>/progress.json `
  --answers-out .private-eval/runs/<tag>/answers.json `
  --stage-export .private-eval/runs/<tag>/stages.json
uv run python scripts/eval_latency_report.py report --answers .private-eval/runs/<tag>/answers.json --label <tag> --out .private-eval/runs/<tag>/latency.json
```

Compare the packet's run against the previous packet's run:

```powershell
uv run python scripts/eval_latency_report.py compare .private-eval/runs/<previous-tag>/latency.json .private-eval/runs/<tag>/latency.json
```

Run notes:

- The **before** numbers for a packet are the **after** numbers of the
  previous packet (L0 provides `L0-a` and `L0-b`). Do not re-run "before"
  unless the previous run is older than 3 days or the stack was changed;
  then re-run it on the previous commit's image and say so.
- The noise band is the absolute difference between `L0-a` and `L0-b` for
  each metric, recorded in L0. A packet's improvement counts only if it is
  larger than the noise band for the metric the packet targets.
- Resume rule: if `--answers-out` exists, only missing question ids run.
  Always use a fresh `<tag>` directory.
- About 12 minutes before the repair, less after. OpenAI latency varies by
  hour; run before/after pairs on the same day when possible.
- The report and compare output contain IDs, timings, and counts only. Do
  not paste answer text or gold text into chat, docs, or commits.

## Git workflow

Remote `origin` is `https://github.com/Nagdy8888/Demo_Project_3.git`
(GitHub serves the renamed repo as `Nagdy8888/smart-rag`; PR links use that
name), default branch `main`, `gh` is logged in as `Nagdy8888`. `main` has no branch
protection, so **you** enforce green checks. The `PR fast` workflow runs on
every push to a PR branch (`preflight`, `format-lint`, `types`, `unit`,
`contract`, `docs-frontend`, `openapi-migrations`, about 11 minutes).

`.private-eval/`, `.env`, and `.env.*` are gitignored. Never force-add
them. `.cursor/plans/` **is** tracked; these plan files are committed by
answer-loss packet A0 together with the answer-loss plan.

### Once, before L0

Nothing to create. Answer-loss packet A0 already cut
`fix/answer-loss-repair` from `main`, committed these plan files, and
opened the draft PR. Check:

```powershell
git checkout fix/answer-loss-repair
git pull --ff-only
git log --oneline -20
```

The log must show the A0, A1, and A2 commits. If it does not, stop:
L0 runs only after A2.

### At the end of every code packet

```powershell
git status --short
```

The list must contain only files the packet touched. Then:

```powershell
git add <every changed/added path from the packet, one by one>
git commit -m "<commit message given at the end of the packet>"
git push
gh pr checks --watch --fail-fast
```

If checks fail: `gh run view --log-failed` on the printed run id, fix the
cause on this branch, commit as `fix(ci): <what>`, push again. Never use
`git add -A`, `git add .`, `--no-verify`, `--force`, or `--admin`. Never
start the next packet on red checks.

## Key paths

| Concern | Path |
| --- | --- |
| SSE attach loop | `apps/backend/src/smart_rag_api/services/sse/service.py` |
| Replay, terminal check, cancel | `apps/backend/src/smart_rag_api/services/sse/replay_cancel.py` |
| Append helpers | `apps/backend/src/smart_rag_api/services/sse/event_append.py` |
| Executor orchestration | `apps/backend/src/smart_rag_api/services/sse/run_orchestration.py` |
| Heartbeat | `apps/backend/src/smart_rag_api/services/sse/run_heartbeat.py` |
| Live-run handles | `apps/backend/src/smart_rag_api/services/sse/registry.py` |
| SSE constants | `apps/backend/src/smart_rag_api/services/sse/constants.py` |
| Stream consume (per-chunk commit) | `apps/backend/src/smart_rag_api/services/sse/langgraph_stream_consume.py` |
| Executor stream + persist | `apps/backend/src/smart_rag_api/services/sse/langgraph_execute.py`, `answer_persistence.py` |
| Run connection | `apps/agents/src/smart_rag_agents/query/runtime/deps_factory.py` (`open_run_app_api_connection`) |
| Event store | `packages/core/src/smart_rag_core/sse/store.py` |
| Connect helper | `packages/core/src/smart_rag_core/settings/postgres_connect.py` |
| Process Hybrid adapter | `apps/agents/src/smart_rag_agents/query/runtime/adapters_hybrid.py` |
| Hybrid retriever | `packages/core/src/smart_rag_core/retrieval/hybrid_run/retriever.py` |
| Channel jobs, temporal lookup | `packages/core/src/smart_rag_core/retrieval/hybrid_run/jobs.py` |
| Hybrid result type | `packages/core/src/smart_rag_core/retrieval/hybrid_run/types.py` |
| Hybrid diagnostics model | `packages/core/src/smart_rag_core/query_routing/models/results.py` |
| Diagnostics builder | `packages/core/src/smart_rag_core/query_routing/branch_channels/hybrid.py` |
| Rerank contract | `packages/core/src/smart_rag_core/retrieval/rerank.py`, `reranker.py`, `rerank_versions.py`, `profiles.py` |
| OpenAI rerank call | `packages/core/src/smart_rag_core/gateways/openai_rerank.py` |
| Rerank prompt | `apps/agents/src/smart_rag_agents/prompts/rerank_v1.md`, `prompts/__init__.py`, `prompts/registry.py` |
| Eval runner | `scripts/run_company_ask.py` |
| Eval stage export | `scripts/eval_ask_stage_export.py` |
| Connection budget | `docs/architecture/05-database-connections.md`, `tests/contract/test_connection_budgets.py` |
| SSE contract doc | `docs/api/SSE.md` |
| Hybrid contract doc | `docs/retrieval/HYBRID_RETRIEVAL_CONTRACT.md` |

## Reporting template (paste at the end of each run)

```text
Packet: L<n>
Files changed: <list>
Tests added/updated: <list>
Commands run and exit codes:
  uv run python -m pytest tests/unit/<...> -q  -> exit 0, N passed
  uv run python scripts/check.py --tier lint   -> exit 0
  uv run python scripts/check.py --tier types  -> exit 0
  uv run python scripts/check.py --tier docs   -> exit 0
Image rebuilt: yes (<probe output>) | no live run in this packet
Timing (latency-12, compare <before-tag> -> <after-tag>):
  <paste the compare table>
  Noise band for the targeted metric: <value from L0>
Done when:
  [pass|fail] <line 1>
  ...
Commit: <sha> "<message>" pushed to fix/answer-loss-repair
PR fast checks: green | red (<failing job>)
Deviations from the packet: <none | describe>
Unverified: <what could not be run and why>
```
