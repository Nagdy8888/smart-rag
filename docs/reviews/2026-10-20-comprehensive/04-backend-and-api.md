# Backend and API review

See [scope and evidence conventions](README.md). Verdict: **good transport and policy foundation; lifecycle retention, execution ownership, and preview workloads need attention**.

## What the backend does well

`main.py` separates app construction from lifespan-owned network resources. Startup binds typed settings, JWKS verification, model gateway, Valkey clients, query runtime, and readiness state. Runtime warmup failures are logged by error type rather than DSN text. Routers, schemas, dependencies, and service modules are generally separated.

Authentication is stronger than merely decoding a JWT: `dependencies/identity.py` uses asymmetric verification, reads the current profile, rejects disabled users, and checks session revocation. Client role headers are confined to a signed test-only mode. Database RPC calls usually bind the server-derived caller identity and authorization version.

Request-body limits enforce declared and streamed bytes for body methods. Error/security middleware provides generic responses, request correlation, restrictive API CSP, and `Cache-Control: no-store`. Rate-limit infrastructure has explicit Valkey/Postgres degraded behavior. Query admission, persisted SSE sequence/replay, cancellation, and reservation settlement have dedicated modules rather than being one endpoint loop.

## BE-01 — P2: finished runs retain private input/context for the process lifetime

**Evidence: reproduced.** `services/sse/registry.py:74-75` maintains `_inputs` and `_contexts`. `drop()` at line 159 removes only `_live`; its docstring intentionally leaves inputs for reconnects. `take_input` and `take_context` use `.get`, so they do not consume the entries.

The synthetic reproduction created and dropped 1,000 runs; `_live` returned to zero while `_inputs` retained 1,000 questions. No TTL, size cap, or removal of these maps was found in this class.

**Impact:** a long-lived API accumulates private question text and authorized runtime contexts. This increases memory use and extends the in-process lifetime of data after a run or conversation is no longer needed. It does not prove cross-user disclosure.

**Recommendation:** delete input/context at terminal completion, cancellation, deletion, and failed start; use a bounded TTL only for the minimal data genuinely needed for a transient pending run. Durable replay already has its own storage. Remove terminal live handles even if no client remains attached.

**Acceptance:** thousands of completed/deleted runs leave bounded registry state, reconnect still replays durable events, and deletion does not leave raw messages in the registry.

## BE-02 — P1 before scaling: process-local start protection does not establish exclusive executor ownership

**Evidence: confirmed control flow; multi-process race not executed.** `run_orchestration.py:114-116` guards `live.started` inside one registry. Its durable `mark_running` delegates to `app.heartbeat_query_run`, which accepts both pending and running states (`20260816170000_query_run_admission_v1.sql:1044`). A mark-running rejection is logged, after which `_start_once` continues toward task creation.

`service.py` prevents many ordinary reconnect restarts by reading durable status. However, two processes can both observe a pending run before either updates it. Both can acquire independent local handles and call a heartbeat that is not an exclusive claim. Normal admission also starts execution, so ownership must cover every start path.

**Impact:** under multiple workers/replicas or overlapping recovery, duplicate execution and provider attempts are possible. Durable usage/event constraints may reject some downstream effects, but are not a substitute for one executor owner. This is not a demonstrated duplicate charge in the current deployment.

**Recommendation:** add an atomic executor claim with owner token and expiry, or a suitable durable lock whose lifetime covers work. On a failed claim, attach/replay only. Stop when mark-running fails; distinguish authorization rejection, already owned, terminal, and temporary storage failure.

**Acceptance:** two separate processes racing admission/attach/recovery produce exactly one provider execution and terminal event; crash recovery acquires a fresh lease after expiry. Until proved, keep a documented single-executor deployment constraint.

## BE-03 — P2: citation page reads are expensive work under a generic read policy

**Evidence: confirmed code; resource exhaustion not load-tested.** `citation_page_http.py:98-104` downloads the entire PDF and renders one page for every read. `storage_admin/objects.py:150-155` uses eager `client.get` and returns `response.content`. The renderer's 40 MiB check occurs after the object is already in memory. The route applies the same 120-attempt low-risk read class used by ordinary run reads.

The renderer bounds page count, pixels, and final PNG bytes, which is good, but there is no application cache or dedicated render-concurrency limit on this path. Generic thread offload avoids blocking the event loop directly; it does not make native rendering or memory free.

**Impact:** repeated authorized previews can repeatedly transfer and parse large PDFs, consume thread capacity, and delay unrelated requests. The low-risk read emergency behavior is a poor fit for comparatively expensive native rendering.

**Recommendation:** stream downloads with a byte cap, enforce a separate preview admission/concurrency policy, and render in a constrained process as SEC-02 recommends. Cache immutable page artifacts by document version/page/render version, while authorizing every read before delivery and honoring deletion/ACL changes.

**Acceptance:** concurrent repeated preview reads have bounded memory and worker usage; oversize downloads terminate before fully buffering; revocation prevents subsequent reads even when an artifact is cached.

## Error handling and fallback semantics

Broad exceptions in the agent verifier and organizer can turn internal failures into apparently usable output. This is not fundamentally a FastAPI error-handler problem: AG-04 changes state before the transport sees it. Keep user-safe errors, but record precise sanitized stage/outcome codes and avoid converting trust failures into verified states.

`FigureHttpService` performs a parameterized ACL-aware query, but uses a fresh database connection per image. Likewise citation preview opens a fresh connection per request. This is a performance investigation target; a pool change should follow measured concurrency and connection-budget evidence rather than assumptions.

## API review coverage and remaining checks

Identity, request limits, preview/figure services, query run routers, SSE start/replay/cancel, readiness, and selected security contracts were inspected. Administrative endpoints and the large PDF evaluation router were sampled, not exhaustively exercised.

Before a release, run authenticated negative scenarios against the actual database: foreign/deleted conversations, revoked sessions, stale authorization versions, downgraded roles, stale document versions, forged object paths, repeated idempotency keys, SSE reconnect/cancel races, and degraded rate-limit stores. The 11 skipped selected contracts do not supply this proof.
