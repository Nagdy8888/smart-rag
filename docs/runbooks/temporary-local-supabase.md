# Temporary local Supabase development

The user authorized this development environment while hosted `smart-rag` recovers
from a full disk. It runs open-source Supabase containers on this laptop and does
not consume hosted database disk or I/O quota.

## Access and resume

- App: <http://127.0.0.1:3000>
- API readiness: <http://127.0.0.1:8000/health/ready>
- Supabase gateway: <http://127.0.0.1:15421>
- Database: localhost port 15422.
- Local login: `.private-eval/local-development-login.txt` (gitignored).

Resume the existing provisioned containers without resetting data:

```powershell
.\scripts\start-local-supabase-dev.ps1
pnpm --filter smart-rag-frontend dev --hostname 127.0.0.1 --port 3000
```

The frontend runs in that terminal. Stop it with Ctrl+C. Stop the local containers
with `docker stop` when needed; retain their volumes. Never use `down -v`,
`supabase db reset`, or `supabase stop --no-backup` on data you want to preserve.

## Isolation and configuration

`docker-compose.local-supabase.yml` overrides the API/worker environment file with
`.env.local-supabase`. The hosted `.env.compose` is retained. The original frontend
configuration is preserved in `.private-eval/frontend-hosted-original.env`.

Supabase CLI 2.121.0 initializes `smart-rag-local-dev` with Postgres 17.11 and
pgvector 0.8.2. The local stack runs Postgres, Auth, PostgREST, Storage, and Kong;
optional Studio, analytics, realtime, and edge services are disabled. Credentials
and ES256 signing keys are private. Runtime connects through a non-superuser login
wrapper with the existing NOLOGIN roles. RLS and JWT verification remain enabled.

The gateway/database containers were explicitly recreated with loopback bindings
because the CLI's network binding option did not produce loopback-only published
ports on this host. Their originals remain stopped with `-pre-loopback` suffixes.
Use the resume script above; a future CLI recreation must recheck actual published
bindings before use. Do not start the originals alongside their replacements.
Docker inspection snapshots and gateway runtime files are private recovery
artifacts, not files to commit or share.

Windows subsequently reserved the original 54321/54322 host ports. The active
containers now publish 15421/15422 on loopback, using the same database volume.
The previous containers remain stopped with `-reserved-port-stopped` suffixes;
never start them against the shared volume. Local recovery image snapshots include
private configuration and must never be pushed to a registry.

## Verified on 2026-10-22

- Fresh replay of all 96 migrations succeeded after fixing a duplicate function
  creation in `20260921150000_sync_document_title_search_terms_v1.sql`.
- Auth password login succeeds and returns ES256 tokens with the configured local
  issuer. JWKS discovery succeeds.
- Authenticated conversation creation returns 201; API readiness is query-ready.
- A real general-knowledge question completes over authenticated API/SSE in 8.9s.
- Local database contains the completed run, 9 checkpoints, 71 checkpoint blobs,
  and 423 checkpoint writes at the smoke-test snapshot.
- Frontend `/login` returns HTTP 200.
- Published gateway, database, and API ports bind to 127.0.0.1.

The first smoke run failed because a pool still held a connection closed during
the local port-binding correction. Restarting the API refreshed the pools; the
second run completed. Both records are retained.

## Remaining boundaries

Browser access was restored. The authenticated local browser suite passed all
42 tests, covering desktop/mobile routes, source citations, streaming, keyboard
access, and visual baselines. Some journeys deliberately stub responses; the
connected question evaluations separately use the real app API/SSE and models.

The original 355-page PDF has now passed the normal scan, review, parse, embed, and
BM25 workflow: 1,206 canonical chunks, 1,134 embedded/BM25 representatives, 40 figure
PNGs, and 20 Parquet tables containing 104 rows. The original hash matches; all
chunks have page locators. Every stored figure hash/image and Parquet row count was
verified. A separate `smart_rag_local` ParadeDB database preserves the older
hosted-derived projection.

The local admin credentials are in `.private-eval/local-admin-login.txt`. Its 50
numbered Mixed50 conversations are visible in app history. Questions, answers,
image evidence, and the report are in `.private-eval/local-mixed50-20261022/`.
All 50 questions ran; 13 are flagged by the recorded checks and spot review.

The local host ingestion worker is running. Its local-only launcher is
`.private-eval/run-local-ingest-worker.py`; its stage log is
`.private-eval/local-ingestion-worker.log`. The older hosted worker launcher still
loads hosted environment files; do not use it for this local corpus.

Hosted Auth users and application rows have not been cloned. The verified archive
contains only checkpoints; local development uses fresh identities and ingestion.

The local API uses the local Compose override with read-only source mounts for
core, agents, and backend code. Dependencies remain pinned in the built image;
restart the API after Python changes, only when no evaluation run is active.
The override disables Python bytecode writes. Do not substitute hosted environment
files when launching this stack. Source hashes, rather than image identity alone,
are needed to reproduce runs. This does not resolve the hosted outage; recovery
remains with the submitted Supabase support ticket.

## Local answer model profile

The user selected GPT-6 Luna for every chat role. The private
`.env.local-supabase` file and example environment use the following profile:

```dotenv
OPENAI_CHAT_MODEL_ID=gpt-6-luna
OPENAI_PROFILE_MODEL_ID=gpt-6-luna
OPENAI_ANSWER_MODEL_ID=gpt-6-luna
OPENAI_VERIFIER_MODEL_ID=gpt-6-luna
OPENAI_SUMMARY_MODEL_ID=gpt-6-luna
OPENAI_CONVERSATION_TITLE_MODEL_ID=gpt-6-luna
OPENAI_EVAL_JUDGE_MODEL_ID=gpt-6-luna
OPENAI_RERANK_MODEL_ID=gpt-6-luna
OPENAI_LIGHTRAG_MODEL_ID=gpt-6-luna
```

The configured local provider's model inventory was checked and includes that
exact ID. All chat roles use it, including page OCR and image descriptions through
the answer role. The existing `text-embedding-3-large` model and vector dimensions
remain unchanged; chat models cannot replace embedding models. Existing corpus
assets are preserved without re-ingestion.

The price table has no verified Luna rate, so usage conservatively retains the
reserved cap. Do not present that cap as a measured provider invoice or assume
this alias exists elsewhere. Per-run cost, token, call, and deadline ceilings
remain unchanged. Earlier mixed-model scores are historical comparisons and do
not establish the all-Luna profile's quality.

Changing the private environment requires recreating the API with the local
Compose files, then checking `/health/ready`. Do this only between evaluation
runs. Merging these examples does not change hosted environment variables or
repair the hosted Supabase project.
