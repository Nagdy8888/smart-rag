# Rules and commands for every packet (general answer-quality repair)

Read this file first in every run, then **exactly one** `G*.md` packet.
Do not read sibling packets. Do not read the big Hybrid/Graph RAG plan or
the older `answer-loss-repair/` packets unless your packet links to one
section of them. Everything you need is in this file and your packet.

Plan index (order, status, acceptance): the file
`.cursor/plans/general_answer_quality.plan.md` (copied into the repo in
G0; until then it lives at
`C:\Users\Nagdy\.cursor\plans\general_answer-quality_repair_ce1b8baf.plan.md`).

## Why this plan exists (read once, 1 minute)

Every new test set scored about 60%. Each repair added code that matched
the failed questions of that set (regexes holding the gold answer words).
The next fresh set failed on different questions, so the score stayed
near 60%. Measured on 130 first-time facts:

- The generated draft held the fact 104 times; the released answer held
  it only 80 times.
- 13 correct drafts were overwritten by question-specific "salvage"
  functions in the verify node.
- 13 correct claims were rejected by the gpt-4o-mini verifier, which
  turned a correct answer into a refusal.
- The salvage functions repaired only 2 wrong drafts.

So this plan (1) builds a fixed measurement loop, (2) deletes
question-specific code, (3) stops the verifier from rejecting verbatim
quotes, (4) optionally adds one locate-quote call, (5) keeps code line
breaks and table structure at ingestion, and (6) proves the result on a
sealed holdout set.
Model stays **gpt-4o-mini** everywhere. No model change is allowed.

## Working rules

1. One packet per run. Do not start the next packet in the same run.
2. Before editing, open every file the packet lists under **Read first**
   and confirm each quoted signature exists. Line numbers may drift by
   a few lines; the function name and body must match. If a signature or
   body differs from what the packet quotes, **stop** and report the
   difference instead of guessing.
3. Where the packet says **exact code**, copy it verbatim. Where it says
   **shape**, keep every name the packet gives and adapt only the glue to
   what the file shows.
4. Every new or changed Python module, class, function, and method gets a
   Google-style docstring (purpose, `Args`, `Returns`, `Raises`,
   `Side Effects` when relevant). Every LangGraph node docstring also
   lists state inputs/outputs, persistence writes, model calls, budget or
   deadline behavior, and the failure route.
5. **General-fix rule (the most important rule).** Never write code,
   prompt text, regexes, constants, or test names that mention a specific
   eval question, page number of the book, gold phrase, book term, class
   name from the book, or eval set id. A change is allowed only when it
   follows from a pattern seen in at least 3 failed questions across at
   least 2 different sets, and it must work for any document. Run
   `uv run python scripts/check_gold_literals.py` (added in G0) before
   every commit; it must exit 0.
6. Never delete or weaken an existing test to make it pass, except the
   tests a packet explicitly allows (G1a and G1b delete tests of deleted
   question-specific functions only, by the procedure in those packets).
7. Never add `TODO`, placeholder returns, `except: pass` without a
   reason, swallowed errors, or a fake success path.
8. Never edit an existing prompt `.md` file (`answer_v1.md` ...
   `answer_v5.md`, `verifier_v*.md`, `rerank_v*.md`), an existing
   `*_SHA256` constant of an old prompt, or a frozen JSON under
   `packages/core/src/smart_rag_core/retrieval/frozen/`. New versions are
   new files.
9. No SQL migrations in this plan. If you think one is needed, stop and
   ask.
10. Docs are part of the change. Each packet lists the docs to update.
    Every new doc gets a row in `docs/README.md`.
11. Never put private questions, gold phrases, answer text, chunk text,
    or raw PDF text into a tracked file, a commit message, a PR body, or
    the chat report. Report counts and question ids only.
    `.private-eval/`, `.env`, and `.env.*` are gitignored; keep it that
    way. Never print `OPERATOR_SUPABASE_DB_URL`.
12. A live run counts as evidence only if the Compose `api` image was
    rebuilt from the current branch first and the probe printed `present`
    for every committed packet (see **Docker rebuild**).
13. If a command fails and the fix is not obvious from the error, stop and
    report the full error. Do not try random changes.
14. **Sealed holdout.** `.private-eval/holdout40-2026-10-v1.json` is run
    exactly twice in the whole plan: once in G0 (baseline) and once in G5
    (acceptance). Nobody reads its per-question results or answers. Only
    the aggregate line, the stage-count table, and the p90 latency number
    are allowed into any report. Tune and debug only on `.private-eval/dev40-2026-10-v1.json`.
15. **Old sets are not targets.** Older private sets (`answer50`,
    `fresh50*`, `mix50`, `fresh30-*`, `unseen50`, `hard50`,
    `known-answer-*`, `mix-hard-24`, `new25`, `rag-agent-10`,
    `answer-ui-24`) were tuned on. Their scores are expected to drop in
    G1a and G1b. Never add code to win them back.
16. **Stop rule.** Each code packet names one target stage in the stage
    report. If the dev40 count for that stage does not go down after the
    packet, or dev40 strict passes drop by more than 3 questions, revert
    the packet's commit (`git revert --no-edit <sha>`), push, and report.
    Do not "fix forward" with new special cases.
17. **After a revert, keep going.** A reverted packet does not block the
    next one. Wherever a packet says "kept" in **Depends on** or compares
    with "the G<x> run", read it as "the last kept packet" and "that
    packet's run" (for example, if G1b was reverted, G2 compares with
    `dev40-g1a`). The evidence doc records `Reverted by stop rule` in that
    packet's `## After` section. G3's gate likewise reads the
    `5a_draft_missing` count from the last kept run.

## Repo facts (verified 2026-10-06)

- OS is Windows; the shell is PowerShell. Run commands from the repo root
  `c:\Nagdy\Mustafa\Work\Upwork\Demo_Project_3`.
- Python: `uv run python ...`. Private scripts under `.private-eval/`
  also work with `.venv\Scripts\python.exe`.
- Set `$env:PYTHONIOENCODING = "utf-8"` before any script that prints
  PDF-derived text.
- One unit test file: `uv run python -m pytest tests/unit/<file>.py -q`.
- Whole unit tier: `uv run python scripts/check.py --tier unit`.
- Contract tier: `uv run python scripts/check.py --tier contract`.
- Lint (Ruff): `uv run python scripts/check.py --tier lint`.
- Types (pyright with baseline): `uv run python scripts/check.py --tier types`.
- Format: `uv run python -m ruff format <paths>` then
  `uv run python scripts/check.py --tier format`.
- Docs (markdownlint, links, Mermaid): `uv run python scripts/check.py --tier docs`
  (about 6 minutes; run once near the end of a packet).
- Everything fast: `uv run python scripts/check.py --tier fast`.
- Current book: document `b56d5774-8810-4ee9-a4d3-f3c93fa90ea7`, version
  `d7e3206a-b262-44d7-90bc-b1572d864c35`, parser
  `parser_v1_pdf_reflow_v4`, 1,005 chunks. The ids are also in
  `.private-eval/ingest-ids.json` (keys `document_id`, `version_id`).
- Gold JSON schema (what `load_private_gold` in
  `packages/core/src/smart_rag_core/evaluation/company_ask_regression.py`
  reads): a JSON array of
  `{"id": str, "page": int, "kind": "code"|"table"|"text", "prompt": str, "facts": [{"id": str, "canonical": [str, ...]}]}`.
  `aliases` is optional per fact.
- The scorer (`phrase_is_present` in
  `packages/core/src/smart_rag_core/evaluation/dual_metric.py`) unescapes
  HTML, folds curly quotes, applies NFKC, and casefolds. It does **not**
  collapse whitespace. A canonical phrase must therefore sit inside one
  source line (code) or one table cell (tables).
- HTML entities such as `&quot;` in streamed answers come from the SSE
  boundary (`security/untrusted.py` `isolate_untrusted_text`). The
  frontend and the scorer decode them. This is **not** a defect; do not
  "fix" it.

## Private files you will use

| File | What it is |
| --- | --- |
| `.private-eval/eval-credentials.json` | Eval login and `base_url` (`http://127.0.0.1:8000`) |
| `.private-eval/dev40-2026-10-v1.json` | 40 dev questions (written in G0). Debug and tune here only |
| `.private-eval/holdout40-2026-10-v1.json` | 40 sealed questions (written in G0). G0 and G5 only |
| `.private-eval/holdout40-2026-10-v1.sha256` | Seal of the holdout file (written in G0) |
| `.private-eval/gold_subset.py` | Writes a filtered gold copy for a subset run |
| `.private-eval/validate_new_set.py` | Validates a new gold set (written in G0) |
| `.private-eval/used-pages.txt` | One comma-separated line of book pages used by earlier sets |
| `.private-eval/ingest-ids.json` | Current book document and version ids |

## Docker rebuild before any live run

The eval calls the laptop Compose API on `http://127.0.0.1:8000`. That
container runs code baked into the `api` image. Nothing you change under
`packages/` or `apps/` reaches the eval until you rebuild.

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

`health/ready` must contain `"query_ready": true`. Then run the probe
(the image is distroless, so only `python -c` works):

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml exec -T api python -c "import importlib as i; v=i.import_module('smart_rag_core.query_answer.versions'); g=i.import_module('smart_rag_core.query_answer.generate_grounded'); r=i.import_module('smart_rag_core.retrieval.rerank'); q=i.import_module('smart_rag_core.query_answer.verifier'); print('G1a', 'present' if v.ANSWER_PROMPT_VERSION in ('answer_v6','answer_v7') and not hasattr(g,'salvage_expose_mode_labels') else 'MISSING'); print('G1b', 'present' if not hasattr(r,'promote_expose_mode_passages') and not hasattr(r,'listed_literal_groups') else 'MISSING'); print('G2', 'present' if hasattr(q,'verbatim_supported_link_ids') else 'MISSING'); print('G3', 'present' if hasattr(v,'LOCATE_PROMPT_VERSION') else 'MISSING')"
```

Every packet already committed must print `present`; later packets print
`MISSING`, which is expected. G3 is conditional: if it was skipped,
`G3 MISSING` is correct. G4 (parser and splitter) has its own probes in
G4b Step 4 and G5 Step 2.

## Live eval commands

One question takes about 25 to 60 s live; 40 questions take about 20 to
40 minutes. Use a fresh output folder per run (the runner resumes from
`--answers-out` if it exists). `--stage-export` is **required** in this
plan because the stage report needs it.

Each packet names its run exactly (for example `$run = "dev40-g2"`);
use that name so later packets can find the folder. If the folder
already exists from a failed attempt, rename the old folder to
`<name>-failed-<yyyyMMdd-HHmm>` first.

```powershell
$run = "dev40-<packet>"
New-Item -ItemType Directory -Force ".private-eval/runs/$run" | Out-Null
uv run python scripts/run_company_ask.py `
  --gold .private-eval/dev40-2026-10-v1.json `
  --out ".private-eval/runs/$run/summary.json" `
  --credentials .private-eval/eval-credentials.json `
  --progress ".private-eval/runs/$run/progress.json" `
  --answers-out ".private-eval/runs/$run/answers.json" `
  --stage-export ".private-eval/runs/$run/stages.json"
```

Run it in the background (Shell with `block_until_ms: 0`) and poll the
progress file with `AwaitShell`; never `sleep` in the shell.

Stage report (added in G0) after every run:

```powershell
uv run python scripts/eval_stage_loss.py --run ".private-eval/runs/$run" --gold .private-eval/dev40-2026-10-v1.json --json-out ".private-eval/runs/$run/stage-loss.json"
```

It prints one line per stage with counts, then `removed_after_draft`
sub-causes, then question ids per stage (ids only). Paste the printed
lines into the report. For the holdout, add `--aggregate-only` (prints
the stage counts without question ids).

Latency p90 (per-question wall time lives in `answers.json` under
`timing.wall_seconds`, not in `summary.json`; nearest-rank p90; prints
numbers only, so it is allowed on the holdout too):

```powershell
.venv\Scripts\python.exe -c "import json,sys; a=json.load(open(sys.argv[1],encoding='utf-8')); w=sorted(float(t['wall_seconds']) for t in ((v.get('timing') or {}) for v in a.values()) if t.get('wall_seconds') is not None); print('timed', len(w), 'of', len(a), 'p90_wall_seconds', w[-(-9*len(w)//10)-1] if w else None)" ".private-eval/runs/$run/answers.json"
```

Subset run: there is no `--ids` flag. Write a filtered copy with
`.private-eval/gold_subset.py`:

```powershell
.venv\Scripts\python.exe .private-eval/gold_subset.py --gold .private-eval/dev40-2026-10-v1.json --ids d01,d07 --out ".private-eval/runs/$run/gold.json"
```

## Git workflow

Remote `origin` is `https://github.com/Nagdy8888/Demo_Project_3.git`,
default branch `main`, and `gh` is logged in. `main` has no branch
protection, so **you** enforce green checks. Work branch:
`fix/general-answer-quality` (created in G0). G0 also parks the
uncommitted fresh-30 work on `wip/fresh30-postfix`; never merge that
branch.

At the end of every code packet:

```powershell
git status --short
```

The list must contain only files the packet touched (untracked
`.private-eval/` and `.cursor/hooks.json` are noise; do not add them).
Then:

```powershell
uv run python scripts/check_gold_literals.py
git add <every changed/added/deleted path from the packet, one by one>
git commit -m "<commit message given at the end of the packet>"
git push
gh pr checks --watch --fail-fast
```

For a deleted file use `git rm <path>`. `gh pr checks --watch --fail-fast`
exits 0 only when every job is green. If it fails, open the failing job
with `gh run view <run-id> --log-failed`, fix the cause on this branch,
commit as `fix(ci): <what>`, and push again. Never use `git add -A`,
`git add .`, `--no-verify`, `--force`, or `--admin`. Never start the next
packet on red checks.

## Key paths

| Concern | Path |
| --- | --- |
| Generate node | `apps/agents/src/smart_rag_agents/query/nodes/answer.py` |
| Verify node | `apps/agents/src/smart_rag_agents/query/nodes/verify.py` |
| Answer gateway (agents) | `apps/agents/src/smart_rag_agents/query/gateway/answer.py` |
| Answer prompt pin (agents) | `apps/agents/src/smart_rag_agents/prompts/__init__.py` |
| Prompt registry | `apps/agents/src/smart_rag_agents/prompts/registry.py` |
| Prompt changelog | `apps/agents/src/smart_rag_agents/prompts/CHANGELOG.md` |
| Answer/verifier pins (core) | `packages/core/src/smart_rag_core/query_answer/versions.py` |
| Grounded answer + salvages | `packages/core/src/smart_rag_core/query_answer/generate_grounded.py` |
| Verifier batch | `packages/core/src/smart_rag_core/query_answer/verifier.py` |
| Answer models | `packages/core/src/smart_rag_core/query_answer/models.py` |
| Requested shape (fence / pipe table) | `packages/core/src/smart_rag_core/query_answer/format_shape.py` |
| Context selection + promotions | `packages/core/src/smart_rag_core/retrieval/context.py` |
| Rerank, seeds, promotions | `packages/core/src/smart_rag_core/retrieval/rerank.py` |
| Fusion models (`ScoredPassage`, `FusionResult`) | `packages/core/src/smart_rag_core/query_fusion/models.py` |
| Model gateway types | `packages/core/src/smart_rag_core/gateways/model_types.py` |
| OpenAI answer/verifier calls | `packages/core/src/smart_rag_core/gateways/openai_answer.py` |
| Usage caps and reserves | `packages/core/src/smart_rag_core/query_admission/usage_caps.py` |
| PDF reflow | `packages/core/src/smart_rag_core/ingestion/parser/helpers.py` |
| PDF adapter | `packages/core/src/smart_rag_core/ingestion/parser/adapters/pdf_adapter.py` |
| PDF parser version | `packages/core/src/smart_rag_core/ingestion/parser/limits.py` |
| Prose splitter | `packages/core/src/smart_rag_core/ingestion/chunking/splitter.py` |
| Chunking version and token limits | `packages/core/src/smart_rag_core/ingestion/chunking/limits.py` |
| Parser test fixtures | `tests/fixtures/parser/__init__.py` |
| Eval runner | `scripts/run_company_ask.py` |
| Stage export | `scripts/eval_ask_stage_export.py` |
| Scorer | `packages/core/src/smart_rag_core/evaluation/dual_metric.py` |

## Reporting template (paste at the end of each run)

```text
Packet: G<n>
Files changed: <list>
Tests added/updated/deleted: <list>
Commands run and exit codes:
  uv run python -m pytest tests/unit/<...> -q          -> exit 0, N passed
  uv run python scripts/check.py --tier lint           -> exit 0
  uv run python scripts/check.py --tier types          -> exit 0
  uv run python scripts/check_gold_literals.py         -> exit 0
Stage report (dev40, before -> after):
  ok                      <a> -> <b>
  1_ingestion             <a> -> <b>
  2_retrieval             <a> -> <b>
  3_fusion_pool           <a> -> <b>
  4_rerank_select         <a> -> <b>
  5a_draft_missing        <a> -> <b>
  5b_removed_after_draft  <a> -> <b>
  strict passes           <a>/40 -> <b>/40
Stop rule: target stage <name> went <down|flat|up>; strict delta <n>; <kept|reverted>
Done when:
  [pass|fail] <line 1>
  ...
Commit: <sha> "<message>" pushed to fix/general-answer-quality
PR checks: green | red (<failing job>)
Image rebuilt for live proof: yes (<probe output>) | no live run in this packet
Deviations from the packet: <none | describe>
Unverified: <what could not be run and why>
```
