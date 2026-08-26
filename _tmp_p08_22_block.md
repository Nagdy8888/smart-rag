## Packet 22 — Run production-like stack, role, visual, and real-answer verification

**Status: BLOCKED.** P08-23 may not merge.

This is a draft evidence section only. It is not committed and does not
check the wrapper packet. No secrets are recorded.

### Requirement (quoted)

> Prove the application works against the real local topology and one bounded
> provider call, with explicit prerequisites and no hidden “when available”
> pass. Required: Docker, repository-supported local Supabase/Compose tooling,
> sufficient disk/ports, approved synthetic fixtures, valid OpenAI credential,
> and available existing query budget. If a credential, entitlement, Docker
> service, or budget is unavailable, record a blocked result and stop.

### Concrete acceptance checks

- Real Generating/Verifying, then a non-empty verified answer or grounded
  refusal.
- At least one durable compatibility `token_delta`.
- Exactly one terminal and correct settlement.
- Role journeys pass, or the packet is explicitly blocked.

### Prerequisite checks (no secret values)

| Check | Result |
| --- | --- |
| `docker version` / `docker info` first pass | Failed. Client 29.6.1; daemon down (`npipe:////./pipe/dockerDesktopLinuxEngine` missing). Exit 1. |
| Docker Desktop start | `Start-Process "C:\Program Files\Docker\Docker\Docker Desktop.exe"` exit 0. Waited ~90s. |
| `docker version` / `docker info` after wait | Passed. Engine 29.6.1, Docker Desktop 4.82.0, context `desktop-linux`, NCPU=20, MemTotal=8131035136, Images=18. Exit 0. |
| Process `OPENAI_API_KEY` | Absent (length 0). User/Machine scopes also absent. |
| `.env` `OPENAI_API_KEY` | present=true, length=164, not a `sk-unit` / fixture. |
| `.env.compose` `OPENAI_API_KEY` | present=true, length=164, not a `sk-unit` / fixture. |
| `.env` / `.env.compose` `MOCK_MODEL_MODE` | present=true, length=5, equals `false`. |
| `.env` / `.env.compose` `SMART_RAG_*` | No uncommented keys. `SMART_RAG_HOLDOUT_ACCESS` absent (not true). Frozen holdout was not opened. |
| Disk | C: used 393.87 GB, free 54.98 GB. |
| Host ports before start | 8000, 3000, 3010, 54321–54325 free. No TCP excluded range covering 54322. |
| Query budget (local `127.0.0.1:54322`) | `company_settings` 1 row, `monthly_llm_budget_usd` NULL (documented default 200). 7/13 profiles have monthly budget min=max 200. Month `llm_usage` cost 0. Budget available. |
| Synthetic fixtures | 13 `auth.users`, 0 `app.documents`. Empty corpus; a grounded refusal would have been an acceptable answer outcome if a run had completed. |

### Documented start commands (not invented)

From `docs/development/LOCAL_SETUP.md`:

- `.\scripts\dev.ps1` then `.\scripts\verify-local.ps1`
- `reset.ps1 -ConfirmReset` is destructive and was **not** run

From `docs/deployment/LOCAL_RELEASE_CANDIDATE.md`:

- Candidate compose is `docker-compose.yml` only
- Prefer `pnpm exec supabase start` plus `docker compose -f docker-compose.yml up` when already migrated

From `docs/development/QUALITY_COMMANDS.md`:

- `docker compose --env-file .env.compose -f docker-compose.yml up -d --no-build --wait --remove-orphans`

Image-context script present: `tests/unit/test_dockerignore.py` (no separate live image-layer secret scanner).

### Commands and results

```text
uv run python -m pytest tests/unit/test_dockerignore.py -q --tb=short
# DOCKERIGNORE_EXIT=0 (1 passed)

pnpm exec supabase start
# first attempt SUPABASE_START_EXIT=1 duration_s=48.2
# LegacyMigrationApplyError: deadlock detected (SQLSTATE 40P01)
# while applying CREATE POLICY job_operation_ledger_worker_rw
# ports 54321/54323–54325 not listening; 54322 TimeWait

pnpm exec supabase stop
# SUPABASE_STOP_EXIT=0 (data preserved; no reset)

pnpm exec supabase start
# SUPABASE_START_RETRY_EXIT=0 duration_s=47.5
# 54321–54325 Listen

uv run python scripts/ops/ensure_app_runtime_role.py
# ENSURE_ROLE_EXIT=0 (password length printed by script: 32; value not recorded)

docker compose --env-file .env.compose -f docker-compose.yml up -d --no-build --wait --wait-timeout 600 --remove-orphans
# COMPOSE_UP_EXIT=0 duration_s=57.2
# api, worker, frontend, paradedb, valkey-limits, valkey-cache, crawl-proxy, clamav healthy
```

Public probes after first compose up (API using `.env.compose` as written):

```text
GET http://127.0.0.1:8000/health/live  -> 200 {"status":"live"}
GET http://127.0.0.1:8000/health/ready -> 200 {"status":"degraded","query_ready":false,"detail":"not_query_ready"}
GET http://127.0.0.1:8000/api/meta     -> 200 {"api_version":"0.1.0","sse_schema_version":"1","min_client_version":"0.1.0"}
GET http://127.0.0.1:3000              -> 200, body contains "Smart RAG"
```

Running API image readiness still requires LightRAG attach for
`query_ready` (`graph == "attached"`). Host source no longer requires that.
In-container `MOCK_MODEL_MODE` is false; `OPENAI_API_KEY` present length 164;
`LIGHTRAG_DB_URL` was empty.

`.env.compose` host labels only (no credentials):

- `SUPABASE_URL` -> hosted `https://qsjivtwtmlmtksufqjik.supabase.co`
- `API_SUPABASE_DB_URL` -> hosted transaction pooler `:6543`
- `WORKER_SUPABASE_DB_URL` -> hosted `:5432`

`.env` has local `SUPABASE_URL` `http://127.0.0.1:54321`. Documented compose
therefore does **not** bind the API to the local Supabase this packet started.

A one-shot attach that copied `API_SUPABASE_DB_URL` into `LIGHTRAG_DB_URL`
made public ready `query_ready=true`, but API/worker logs showed LightRAG
connecting to the hosted pooler on `:6543` (prepared-statement error on
worker). That path was reverted immediately:

```text
# process env LIGHTRAG_DB_URL=""
docker compose --env-file .env.compose -f docker-compose.yml up -d --no-build --wait --wait-timeout 180 api worker
# COMPOSE_REVERT_EXIT=0; api+worker healthy
```

API/worker were then recreated with **process-env only** (files not rewritten)
to local session topology: `SUPABASE_URL=http://host.docker.internal:54321`,
DB/checkpoint/LightRAG DSN `host.docker.internal:54322` as `app_runtime`.

```text
# COMPOSE_LOCAL_EXIT=0
GET /health/live  -> 200 {"status":"live"}
GET /health/ready -> 200 {"status":"ready","query_ready":true,"detail":"ok"}
GET /api/meta     -> 200 handshake versions as above
API log: Connected to database at host.docker.internal:54322/postgres
```

### Smallest real-provider browser attempt

- Created one local GoTrue member via Auth Admin (email
  `p08-22-db70979afd43@example.com`; password not recorded). Profile monthly
  budget 200. Holdout not opened.
- Started `pnpm dev --port 3010 --hostname 127.0.0.1` with local
  `NEXT_PUBLIC_*` (pinned demo anon JWT from `playwright.config.ts`).
- Browser: `http://127.0.0.1:3010/login` then Ask `/`.
- GoTrue `POST /auth/v1/token?grant_type=password` -> 200 (local `:54321`).
- Ask chrome showed `Ready`. Send enabled after typing.
- `POST /conversations` -> 201. Conversation
  `d7cecc42-7353-465a-a574-92820e96b7db` exists in local `app.conversations`.
- `POST .../messages` -> 202. `GET /runs/{id}/events?after=0` -> 200.
- `GET /ops/ready` -> 403 (expected for member).
- Pipeline labels Preparing/Retrieving/Generating/Verifying are always in
  the DOM; a `waitFor Generating` match is **not** proof of a live stage.
- `waitFor Verifying` timed out (5s). No non-empty verified answer or
  grounded refusal appeared.
- Local durable proof after the send:

```text
app.conversations target row: 1
app.messages for that conversation: 0
app.runs total: 0
app.run_events for the advertised run id: 0
app.llm_usage for that run: 0 cost / 0 tokens / 0 rows
UI Terminal stayed "running"; Stage "— / —"; Sources (0); usage 0/0
```

No durable `token_delta`, no one terminal, no settlement, no provider spend
row. Treating this as a successful chat outcome is forbidden.

### Authorization / failure / fallback

- Public `/health/ready` omits named dependencies (status/query_ready/detail
  only). Proven.
- Member `/ops/ready` 403. Proven.
- Send remains gated on `query_ready` in current frontend
  (`paidSendBlockReason`). First compose pass blocked Send until LightRAG
  was attached on the running image.
- Hosted-pooler LightRAG attach is not an approved local proof and was
  reverted. No holdout access flag was set.
- Empty-success chat (202/SSE 200 without persisted run/message/usage) is
  recorded as failure, not pass.

### Unverified / not run

- Clean image-layer secret inspection beyond `test_dockerignore.py`.
- Role Playwright journeys and 390/1280 visual baselines.
- Reconnect/resume, cancel, 402/403/426/429, revoked session, BM25/graph
  degradation.
- `verify-local.ps1` (asserts ready substring `unconfigured`; incompatible
  with real-provider `query_ready=true`).
- Hosted query budget / hosted documents (not queried after the pooler
  attach was seen).
- P08-21 wrapper item was not re-checked (forbidden for this run).

### Deviations

- Did not run `dev.ps1 --build` or `reset.ps1`. Used documented
  `supabase start` + `docker compose ... --no-build --wait`.
- First `supabase start` deadlocked on a migration policy; retry after
  `supabase stop` succeeded without reset.
- Temporary process-env override was required because `.env.compose` points
  API/worker at hosted Supabase/pooler, while this packet started local
  Supabase. Files were not rewritten.
- One mistaken LightRAG attach used hosted `API_SUPABASE_DB_URL` (`:6543`).
  Reverted. Do not repeat.
- Leftover `vibrant_wing` gitleaks container was already running after
  Docker came up; not used as image-layer proof.

### Rollback

- Local Supabase and Compose remain up for operator inspection.
- Hosted LightRAG attach was reverted; API/worker last recreated against
  local `54321`/`54322`.
- No plan file checked. No commit. No merge.

### Handoff blockers

1. P08-22 is **BLOCKED**. Do not mark packet 22 complete. P08-23 may not merge.
2. Real-provider browser query did not produce Generating/Verifying progress,
   a verified answer or grounded refusal, `token_delta`, or one terminal.
3. `.env.compose` is hosted-oriented; documented compose up is not the local
   candidate topology until those keys are local session DSNs (not `:6543`).
4. Running API image still requires LightRAG attach for `query_ready`.
5. Durable admit/SSE path created a conversation but no `app.runs` /
   `app.messages` / `app.llm_usage` row for the live send.
