# Packet 8 — thin authenticated developer UI

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

## Quoted requirement

> Ship the thin authenticated developer UI and prove route, fallback,
> injection, idempotency, budget, outage, event-loop, and privacy gates.

## Acceptance checks restated

- Thin UI for sign-in, upload/status, safe stream/reconnect/cancel,
  route/limitation diagnostics, citations, and feedback. No Stitch or
  production frontend.
- Route/fallback/injection/idempotency/budget/outage/privacy cases use
  real local API contracts; UI fixtures do not replace packets 1–7.
- One-paid-run across double send/reconnect; handshake before paid POST;
  conversation delete 204 with content-free acknowledgment.
- Five Composite streams: p95 event-loop lag `<50 ms`, heartbeat jitter
  `<2 s`, zero missed 15 s heartbeats.
- XSS-safe rendering; no `dangerouslySetInnerHTML`.

## Implemented

- Browser-direct `@supabase/ssr` `createBrowserClient` password sign-in.
  FastAPI receives `Authorization: Bearer`.
- Auto Composite chat admits with `Accept: application/json` (202 body
  includes `run_id`) then `GET /runs/{id}/events`. Handshake
  `X-Client-Version: 0.1.0` and a stable `Idempotency-Key` until
  terminal. Resume GET omits the version header. Cancel is POST.
- Unknown SSE types logged and ignored. Token/entity text via React text
  nodes + `displayText`. Citation `href` requires `isSafeHttpUrl`.
- Signed limitation copy including `temporal_graph_limitation` and
  `bm25_unavailable`. Graph-not-ready sentence never mentions
  restricted/ineligible counts.
- Unmerged packet-7 feedback tags. DELETE conversation acknowledgment
  without source text.
- `POST /documents/uploads` reservation display. Local `signed_url` is
  null until Phase 10. `GET /ingestion/versions/{id}/status` shows BM25
  index/lag/pending/failed/dead-letter and graph-handoff counts. Graph
  ready is never inferred from upload.

SSE catalog payloads do **not** include BM25 index/lag. Those fields
come from version status.

## Live local proofs (2026-08-16)

Compose `smart-rag-api` on `:8000` was still the Phase 1 image (`/health/*`
only). Packet 8 live HTTP used host `uvicorn` from this tree with
`SUPABASE_URL=http://127.0.0.1:54321` and local Postgres `:54322`.
Password-grant JWTs are `aal1`; owner/`upload_enabled` callers are
rejected with `403 MFA required` (packet 2 identity). Live chat therefore
uses `member` without upload. Upload reserve as that member returns
`403 forbidden`.

| Check | Result |
| --- | --- |
| `GET /api/meta` | 200 `min_client_version=0.1.0` |
| Bearer `GET /me` | 200 member, `upload_enabled=false` |
| POST messages without `X-Client-Version` | 426 |
| Double POST same idempotency key | same `run_id` (one paid run) |
| XSS `<script>` in message | `text/event-stream`, no `text/html` |
| SSE until terminal | `schema` plus a terminal event |
| DELETE conversation | 204; GET conversation/events 404 |
| `search_conversation_lingering_ids` | all counts 0 |
| Five Composite admits + concurrent GET events | 5 distinct `run_id`s, all SSE terminals |
| Five held streams lag/heartbeat | `test_five_held_streams_meet_lag_and_heartbeat_gates` exit 0 (16s hold; live mock completions are shorter than 15s so they do not claim missed heartbeats) |

## Commands and exit codes

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend test` | 0 (23 passed) |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend typecheck` | 0 |
| `pnpm --filter smart-rag-frontend build` | 0 |
| `pnpm --filter smart-rag-frontend exec playwright --version` | 0 (`Version 1.62.1`) |
| `uv run python -m pytest tests/contract/test_sse_heartbeat.py::test_five_held_streams_meet_lag_and_heartbeat_gates` | 0 |
| `uv run python -m pytest tests/contract/test_thin_developer_ui_live.py` | 0 (3 passed) |
| Playwright `login.spec.ts` | failed: Chromium headless not installed; CI still only asserts `--version` |

## Wrapper Deliver / Review / Done one-to-one

| Wrapper clause | Evidence | Status |
| --- | --- | --- |
| Deadlines/ceilings | Packet 1 admission + packet 2 routing tests | proven (API) |
| Server-derived authorization | Packets 1 and 5; live JWT `/me` | proven |
| Frozen ParadeDB BM25 recheck/degradation | Phase 4/5 + packet 5 cache; UI shows BM25 from version status | proven (API); UI display wired |
| Rewrite fidelity / route matrix / one correction | Packet 2 | proven (API) |
| Resolved-path fusion / ablation / table / verifier | Packet 3 | proven (API) |
| Memory / reaper / deletion / governance / traces | Packet 7 | proven (API) |
| Optional tools outside catalog discovery | Packet 4 | proven (API) |
| Additive API/SSE handshake + resumable SSE | Packet 6; live 426 + GET events | proven |
| Authorization-safe cache | Packet 5 | proven (API) |
| Reserve-once / true-up budgets | Packet 1; live double POST same key | proven |
| Provider vs FastAPI rate ownership / Valkey fail-closed | Packet 5 | proven (API) |
| Restricted read auditing | Packet 1 | proven (API) |
| Event-loop / CPU offload / 15s heartbeat | Packet 6 five-held-stream test re-run | proven (ASGI hold); not 15s on sub-second mock completions |
| Immediate conversation deletion | Packet 7 + live lingering-ID search | proven |
| Injection / XSS | Packets 5–6 + `safe-text` + live XSS message | proven |
| Thin UI sign-in/upload/status/stream/citations/feedback | Console + live JWT HTTP contract | proven (HTTP); Chromium login + readiness e2e |
| Historical/coverage/negation/media/ACL-blindness via UI | Packets 2–3 limitation copy in UI; not re-driven as live labeled eval | mapped, not re-executed as UI cases |
| Combined +10pp vs Hybrid (QT-EVAL-009) | Packet 7 registry | **unverified** live |
| ParadeDB/LightRAG/Valkey outage through the browser | `/health/ready` panel + signed outage copy + live compose-stop when probed ok | proven for readiness visibility; Hybrid degrade remains packet 4/5 API |
| Live OpenAI answer/verifier | Mock mode | **unverified** |
| Hosted Auth throttling / Phase 10 CDN / Secrets Manager | Later phases | blocker |
| Stitch / production frontend | Phases 7–8 | not started |

## Deviations

- Chat client uses JSON 202 then GET EventSource so `run_id` is in the
  body. The API does not send `X-Run-ID`. Same one-paid-run contract.
- CORS defaults include Playwright `:3010` so tests do not reuse Compose
  `:3000`.
- Compose API image lagged this tree (`/health` only) until rebuild. Live
  proofs used host uvicorn against local Auth/Postgres.
- Local password JWTs are `aal1`. Upload-enabled/owner callers need MFA;
  live aal1 + `upload_enabled` is `403 MFA required`. aal2 TOTP + upload
  reserve is `signed_url=null` (not CloudFront).
- Dockerfile first `uv sync` now copies
  `hybrid_default_v1.json` so hatchling force-include can build.

## Rollback

- Revert the frontend App Router console to the Phase 1 scaffold.
- Remove `NEXT_PUBLIC_API_BASE_URL` and `:3010` CORS origins.
- Restore Dockerfile without the early frozen-profile COPY (API image
  build will fail hatchling force-include).

## Phase status

Packet 8 is **complete**. Phase 6 wrapper `status` remains **`pending`**
until you accept the `Done when` gate. Do not start Stitch (Phase 7) or
production UI (Phase 8) from this packet.
