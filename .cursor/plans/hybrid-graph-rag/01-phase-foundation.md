---
name: hybrid-graph-rag-phase-01-foundation
phase: 1
status: pending
depends_on: []
source_plan: ../hybrid-graph-rag_ab5281ef.plan.md
global_contract: ./00-global-contracts.md
---

# Phase 1: Foundation

## Mandatory model loading contract

1. Read [`00-global-contracts.md`](./00-global-contracts.md) first, then read this file completely.
2. Treat this file as the only implementation scope for Phase 1. Later-phase files may clarify an interface but do not authorize later-phase implementation.
3. Inspect the current repository, schemas, migrations, tests, and pinned dependency versions before editing. This plan describes targets, not proof that a file or API already exists.
4. Load the relevant workspace skill files listed below before implementation.
5. Before every work packet, state the requirement and concrete acceptance checks. Implement the smallest complete packet.
6. Verify unstable external APIs against current primary documentation and add contract tests. Never guess a library method, schema, environment variable, command, or provider behavior.
7. Add positive, failure, authorization, idempotency, bounded-resource, and fallback tests whenever applicable.
8. Run repository-defined format, lint, strict type, test, build, migration, and integration commands relevant to changed files. Phase 1 must define these commands; later phases must inspect rather than invent them.
9. Update documentation in the same change. Do not leave placeholders, fake success paths, swallowed errors, disabled security, or `TODO` core behavior.
10. Record proof in the exit record. If security, data semantics, cost, or acceptance criteria must change, stop and obtain approval through an ADR/plan update.

## Prerequisites

No earlier implementation phase; global target sign-off is still required.

## Relevant workspace skills

- [`.cursor/skills/scaffold-monorepo-layout/SKILL.md`](../../../.cursor/skills/scaffold-monorepo-layout/SKILL.md)

## Scope lock

**In scope:** Repository initialization, approved monorepo boundaries, local service skeleton, configuration, quality gates, CI tiers, and documentation foundations.

**Out of scope:** Application retrieval, ingestion, GraphRAG, production UI, managed cloud infrastructure, and real corpus processing.

The scope lock controls implementation sequencing; it does not weaken any security, authorization, durability, budget, grounding, bounded-work, or documentation invariant in the global contract.

## Ordered work packets

Complete these in order. A checked box requires committed implementation evidence in the phase exit record, not only code presence.

1. [x] Obtain and record sign-off for quality, capacity, distinct normal/graph-maintenance budgets, RTO/RPO, availability/workload-isolation triggers, v1 media limitations, and dated Hybrid Pilot decision criteria.
2. [x] Create the exact uv/pnpm workspace and dependency directions; add one lockfile per ecosystem and one LangGraph project file.
3. [x] Create local Docker/WSL2 helpers, a digest-pinned private ParadeDB/`pg_search` service, split private Valkey services, the crawl-proxy boundary, mock-model mode, and health checks.
4. [x] Add typed settings, structured logging, non-root images, import-boundary checks, docstring enforcement, and hard-failing quality commands.
5. [x] Create tiered CI and the required documentation index, architecture skeleton, ADRs, risk register, OpenAI/subprocessor governance packet drafts, migration/API compatibility policies, local admin-alert contract, and Hybrid Pilot decision record.
6. [ ] Prove one-command local startup and all Phase 1 fast gates, then record evidence before Phase 2 starts.

## Cheap-model execution protocol

The six checkboxes above are separate work packets. One model run may execute only one packet. Before editing, the model must quote that packet, list its concrete acceptance checks, inspect every target path, and distinguish confirmed existing files from plan-prescribed files that still need creation.

Use [`docs/development/phase-01-foundation-evidence.md`](../../../docs/development/phase-01-foundation-evidence.md) as the canonical packet evidence file. Packet 1 creates it even though the full documentation index is created later. Each packet appends its requirement, inspected paths, exact commands and exit codes, files changed, negative/failure checks, unresolved assumptions, and handoff. Packet 5 links it from `docs/README.md`. Do not check a packet from file presence alone.

For every dependency, image, CLI, configuration format, or GitHub Action:

1. inspect the current repository and host tool availability;
2. verify the current primary documentation and licensing terms;
3. select and record the exact version, immutable image digest, package-manager resolution, or commit SHA;
4. generate the root lockfile from the selected metadata;
5. run a real load/build/contract check; and
6. record the source URL, selected version, command, and result in the packet evidence.

Never invent a dependency version, ParadeDB digest, `pg_search` DDL/API, LangGraph config field, Supabase CLI command, service health result, or GitHub Action SHA. If it cannot be verified, stop that packet. A generated lockfile is evidence of resolution, not evidence that an integration works.

Phase 1 may create minimal executable boundaries, but they must fail honestly outside Phase 1 capability. A liveness endpoint may prove only that its process is running. A readiness endpoint must report `unconfigured`, `starting`, or `degraded` when required dependencies are absent; it must not return ready because a socket opened. Query/ingestion graph scaffolds may be loadable for configuration qualification but must not expose a fake successful query or ingestion path. The crawl proxy starts deny-by-default until Phase 3 adds approved destination policy. No placeholder may claim authentication, retrieval, ingestion, graph, migration, backup, or managed-cloud behavior.

Documentation statuses have fixed meanings:

- `planned`: the owning later phase and acceptance target are identified, but no behavior exists;
- `draft`: substantive policy content exists but external or user review is pending;
- `proposed`: an ADR has options and a recommendation but no approval;
- `accepted`: the named approver and decision date are recorded;
- `verified`: the documented command or drill has executed successfully and the evidence location is linked.

Do not use `accepted`, `signed`, `complete`, or `verified` without the corresponding approval or command evidence. At most two bounded repair attempts may be made for the same failing external/tool contract before stopping with the exact error and rollback state.

## Work packet implementation contracts

### Packet 1 — targets, budgets, and human sign-off

#### Packet 1 preconditions

- Read the global contract and this phase completely.
- Confirm that this packet is documentation-only and that no prior signed target record already exists.
- Inspect `docs/`, the current plan-review record, and prior reviews without treating historical values as current approval.

#### Packet 1 allowed outputs

- [`docs/QUALITY_TARGETS.md`](../../../docs/QUALITY_TARGETS.md).
- [`docs/adr/ADR-hybrid-pilot-release-cut.md`](../../../docs/adr/ADR-hybrid-pilot-release-cut.md).
- [`docs/development/RISK_REGISTER.md`](../../../docs/development/RISK_REGISTER.md).
- [`docs/architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md`](../../../docs/architecture/AVAILABILITY_AND_ISOLATION_TRIGGERS.md).
- The initial [`docs/development/phase-01-foundation-evidence.md`](../../../docs/development/phase-01-foundation-evidence.md).

#### Packet 1 forbidden outputs

- Application code, lockfiles, containers, migrations, CI workflows, provider configuration, or dependency selection.
- Fabricated approver names, dates, measured latency/cost, or client acceptance.
- Merging the normal-operation OpenAI ceiling with the graph compliance/maintenance reserve.

#### Packet 1 ordered actions

1. Copy every provisional measurable target from the global contract into `QUALITY_TARGETS.md` without changing its value or meaning. Give each target an identifier, unit, provenance link, approval status, approver, approval date, measurement phase, and failure response.
2. Record capacity, all route latency/deadline/model-call/tool ceilings, ingestion and graph throughput, chunking, retrieval/evaluation/query-profile gates, BM25 qualification targets, temporal policy, RTO/RPO, and availability triggers.
3. Record normal operation (`USD 200/month` plus `USD 20/ingestion day`) separately from the graph reserve formula (`max(USD 800, 4 × measured full-rebuild cost)`). State that the formula cannot be evaluated until a measured rebuild exists and that normal budgets cannot consume the reserve.
4. Record the v1 media limitation: text, OCR output, typed tables, and adjacent captions are supported; materially figure/chart/diagram-only evidence produces a limitation notice. Link the planned vision-captioning ADR.
5. Record UTC as the provisional temporal policy and state that Hijri dates are non-authoritative in v1 unless a separately approved parser/fixture contract is added.
6. Create the Hybrid Pilot ADR with named approver fields, dated end-of-Phase-1 and end-of-Phase-4 checkpoints, and objective continue-versus-pilot criteria: Phase 1 gate status, Phase 4 Hybrid gates, revised Phase 5 estimate, SME availability, approved remaining budget, and explicit acknowledgement that a pilot is not production v1.
7. Create the risk register with owner, probability, impact, mitigation, trigger, review date, and evidence link. BM25 full-envelope resource/rebuild values, graph rebuild cost, local hardware sufficiency, provider governance, and user sign-off remain assumptions until measured or approved.
8. Copy the exact global availability and workload-isolation triggers into their canonical document with an owner and required review action.
9. Ask the user to approve all provisional defaults or provide replacements. Record their exact decision; do not infer consent from silence.
10. Append packet evidence and stop if any required sign-off remains unresolved.

#### Packet 1 acceptance checks

- Every numeric target in global-contract lines 63–81 is represented once, with units and provenance, and no contradictory duplicate exists.
- Capacity explicitly covers 10,000 Hybrid document versions, 1,000,000 chunks, 25 active users, five simultaneous runs, and the 2,000-document/200,000-chunk initial graph envelope.
- Normal and maintenance budgets, media limitation, UTC/Hijri policy, RTO/RPO, and every multi-host trigger are separately visible.
- Hybrid Pilot checkpoints contain actual dates, an approver field, objective criteria, and the production-label prohibition.
- The user has explicitly approved the defaults or approved recorded replacements. Otherwise packet 1 and Phase 1 remain blocked.
- Only the allowed documentation paths changed, and packet evidence lists pending versus approved fields.

#### Packet 1 stop routes

- A requested change affects security, data semantics, cost, or acceptance criteria: create an ADR/plan amendment and obtain approval before changing the canonical value.
- An approver or checkpoint date is unavailable: leave the record `proposed`, report the blocker, and do not start packet 2.

### Packet 2 — reproducible uv/pnpm workspace and dependency boundaries

#### Packet 2 preconditions

- Packet 1 has explicit approval evidence.
- Load the monorepo scaffold skill and inspect the repository for newly created or conflicting paths.
- Verify current uv workspace, Hatchling, pnpm workspace, Next.js scaffold, and LangGraph configuration contracts from primary documentation before selecting versions.

#### Packet 2 allowed outputs

- Root `pyproject.toml`, `uv.lock`, `package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`, `.gitignore`, and tool-version documentation.
- The four Python members and import roots prescribed in Section 3: `apps/agents/src/smart_rag_agents`, `apps/backend/src/smart_rag_api`, `apps/worker/src/smart_rag_worker`, and `packages/core/src/smart_rag_core`.
- `apps/frontend` as the sole pnpm application member.
- The single `apps/agents/langgraph.json`.
- Minimal import/load tests and architecture-boundary tests under `tests/unit` and `tests/contract`.

#### Packet 2 forbidden outputs

- Auth, RLS, migrations, queues, parsers, embeddings, retrieval, LightRAG, BM25 adapter behavior, agent routing, production UI, or provider calls.
- A second lockfile or `langgraph.json`; member-local virtual environments or generated dependency files committed as source.
- Historical PO/image/Airtable/GAS code, local upload persistence, speculative `shared`/`common`/`utils` packages, or path-shorthand dependencies.
- A graph or API route that returns fake business success.

#### Packet 2 ordered actions

1. Record the verified tool/package versions and primary-documentation links before authoring metadata.
2. Create the non-distributable root uv workspace with exactly four Python members. Use the exact distribution/import pairs and Hatchling `src/` wheel targets in this phase.
3. Declare direct workspace dependencies by distribution name: agents to core; backend to agents and core; worker to agents and core; core to no app. Add matching root `[tool.uv.sources]` entries.
4. Create the pnpm workspace with only `apps/frontend` plus root tooling. Configure TypeScript strict mode and a production-buildable Next.js App Router foundation without Stitch integration or auth.
5. Create only the package modules needed for import, process startup contracts, and the target directory ownership. Do not fill future domain directories with deceptive implementations.
6. Create one LangGraph project file using the verified schema and register query and ingestion graph exports. Qualification is config/load behavior only; invocation must not claim query or ingestion completion.
7. Generate `uv.lock` and `pnpm-lock.yaml` from the repository root. Never hand-edit resolved package entries.
8. Add boundary tests that scan imports and fail on every forbidden direction in Section 3. Include intentional negative fixtures or isolated temporary files proving that the checker actually fails.
9. Run locked install, distribution/import smoke checks, frontend production build, and the verified LangGraph config loader.
10. Append versions, commands, results, and any unverified integration behavior to packet evidence.

#### Packet 2 acceptance checks

- Exactly one `uv.lock`, one `pnpm-lock.yaml`, and one `langgraph.json` exist in the entire repository.
- uv members and pnpm members exactly match the prescribed list; package names, import roots, wheel targets, and direct dependencies match Section 3.
- Core contains no app import; frontend imports no Python workspace source; backend/worker/agents boundaries pass both positive and intentional-negative tests.
- Each Python distribution installs/imports from the locked root workspace.
- The frontend production build succeeds with strict TypeScript and no mock auth/retrieval claim.
- LangGraph configuration loads both graph IDs using the verified pinned contract; evidence does not claim business execution.
- No out-of-scope application, database, retrieval, ingestion, graph, or managed infrastructure behavior was added.

#### Packet 2 stop routes

- Current primary docs contradict the planned LangGraph or workspace format: stop and propose an ADR/plan amendment rather than guessing.
- Dependency resolution requires weakening a pin or boundary: stop with resolver output.
- A new top-level package or reversed edge appears necessary: obtain ADR and plan approval first.

### Packet 3 — local private-service topology and honest health

#### Packet 3 preconditions

- Packet 2 locked installs and boundary checks pass.
- Verify current Docker Compose, Supabase CLI, ParadeDB/`pg_search`, Valkey, and base-image documentation and licenses.
- Resolve and record immutable container digests. A tag alone is insufficient.

#### Packet 3 allowed outputs

- Local `docker-compose.yml`, `.env.example`, PowerShell/WSL2 start-stop-reset helpers, deployable Dockerfiles, and versioned `infra/paradedb/` assets.
- A deny-by-default crawl-proxy foundation under `infra/crawl-proxy/`.
- Local Supabase CLI configuration without application schema/RLS migrations.
- ADRs `docs/adr/ADR-paradedb-edition-availability.md` and `docs/adr/ADR-private-service-tls.md`.
- Liveness/readiness contracts and tests for foundation services.

#### Packet 3 forbidden outputs

- Managed Supabase linkage, AWS credentials/resources, CloudFront/WAF/SES, production provisioning, or fake `docker-compose.prod.yml` evidence.
- Public host ports for ParadeDB, either Valkey service, LightRAG, or the crawl proxy.
- One shared Valkey instance, unauthenticated Valkey, unpinned images, unrestricted crawl egress, or provider secrets in images/Compose.
- Identity schema, application migrations, BM25 projection jobs/index, LightRAG tables, real crawling, or live OpenAI requirements.

#### Packet 3 ordered actions

1. Verify the ParadeDB edition, `pg_search` availability, image source, digest, license, and health/extension query from current primary sources. Record alternatives and the selected edition in the ADR. Stop if no approved digest can be verified.
2. Decide same-host private-network TLS for ParadeDB and Valkey in the TLS ADR before omitting or enabling TLS. Record threat model, compensating controls, credential rotation owner, and the staging/production revisit trigger.
3. Build Python images from the repository root context. Copy workspace metadata before sources for caching; sync the selected package with `uv sync --locked --package <distribution> --no-dev`; use non-root runtime users and read-only/minimal runtime permissions where compatible.
4. Create separate authenticated Valkey limit and cache services. Limits use `noeviction`; cache uses an explicitly bounded evicting policy. Give them distinct credentials, volumes only when justified, health checks, and private networks.
5. Add ParadeDB with no host port, least-privilege bootstrap/writer/reader role intent, persistent local volume, resource limit, and a health check that verifies the qualified extension rather than TCP alone. Application projection DDL remains Phase 2/4-owned.
6. Add a crawl proxy that exposes only an internal service port, has no ambient secrets, returns healthy while denying all outbound targets by default, and has a negative test proving private/public fetches are blocked until Phase 3 policy is implemented.
7. Pin a reproducible Supabase CLI invocation after current-doc verification. The local stack may start with stock Phase 1 configuration only; Auth policy, schema, Storage buckets, RLS, and application migrations remain Phase 2.
8. Define `.\scripts\dev.ps1`, `.\scripts\stop.ps1`, and an explicit destructive reset helper. `stop` preserves volumes; reset requires confirmation and never runs implicitly. Provide a WSL2 shell equivalent only if it invokes the same Compose/config contract.
9. Define process liveness and dependency-aware readiness. Backend/frontend/worker may report live independently; they report not-ready or degraded when required local dependencies are unavailable. Worker health must not claim queue processing before Phase 3.
10. Validate Compose rendering, image builds, non-root users, private port exposure, resource limits, authentication, deny-by-default proxy behavior, and mock-profile startup.
11. Append image digests, ADR decisions, network/port inventory, commands, negative tests, and remaining Phase 2 dependencies to packet evidence.

#### Packet 3 acceptance checks

- Every third-party/base image is immutable-digest pinned and its provenance is recorded.
- ParadeDB, both Valkey services, and crawl proxy have no public host port. Only explicitly documented developer endpoints are published.
- Two authenticated Valkey services have distinct roles, credentials, memory limits, and eviction policies.
- ParadeDB health verifies the qualified `pg_search` contract; no canonical application data is stored or claimed.
- Crawl proxy is healthy but denies all destinations by default, with a passing negative test.
- All application images run non-root and locked; no AWS or live OpenAI credential is required.
- Start/stop/reset semantics and Supabase CLI prerequisites are explicit; stop preserves data.
- ADRs are accepted by a named approver before a same-host TLS omission or ParadeDB edition assumption is treated as final.

#### Packet 3 stop routes

- Missing Supabase CLI, Docker/WSL2 resources, ParadeDB digest/license evidence, or TLS approval blocks packet completion; report the exact prerequisite rather than substituting an easier service.
- A private service requires a public port to pass tests: fix test topology; do not publish it.

### Packet 4 — settings, observability, and hard-failing quality gates

#### Packet 4 preconditions

- Packets 2 and 3 pass locked build/topology checks.
- Inspect all authored modules and current tool configuration before adding enforcement.

#### Packet 4 allowed outputs

- Pydantic Settings modules per deployable, shared setting primitives with no framework imports, structured JSON logging, correlation middleware/lifecycle wiring, and deterministic mock-model boundary behavior.
- Root Ruff, Pyright strict, pytest, pre-commit, ESLint, TypeScript strict, Vitest, Playwright, Markdown, and Mermaid tool configuration.
- AST docstring, import-boundary, lockfile/project-count, configuration, logging, health, and mock-network-denial tests.
- A canonical cross-platform `python scripts/check.py --tier <name>` command surface plus root package scripts.

#### Packet 4 forbidden outputs

- Scattered `os.getenv`, import-time provider clients, raw secret/source logging, broad `Any`, swallowed exceptions, permissive client errors, disabled lints/types/tests, or `|| true`.
- Real OpenAI calls in fast tests; real auth/retrieval/ingestion behavior; security checks that only scan comments or never execute a negative fixture.

#### Packet 4 ordered actions

1. Add deployable settings that validate at startup, document every environment variable/default/security classification, and fail with a sanitized message. `.env.example` contains placeholders only.
2. Add structured JSON logs with timestamp, level, service, environment, event name, request/run/job correlation IDs when applicable, and sanitized exception metadata. Tests assert secrets and unrestricted source content are absent.
3. Implement mock-model mode as a deterministic, bounded test adapter behind the core gateway boundary. It must make network OpenAI calls impossible in mock mode and identify fixture provenance; it must not imitate unimplemented retrieval success.
4. Configure Ruff format/lint/pydocstyle, Pyright strict, pytest, pre-commit, ESLint, TypeScript strict, Vitest, Playwright, Markdown lint/link checks, and Mermaid syntax/render tooling at verified pinned versions.
5. Add an AST test covering every authored Python module/class/function/async function/method, excluding only explicitly recognized generated/vendor paths. Test the checker against an intentional missing-docstring fixture.
6. Add lockfile/single-project and import-boundary checks with intentional negative fixtures.
7. Create `scripts/check.py` with documented tiers `format`, `lint`, `types`, `unit`, `contract`, `docs`, `frontend`, and `fast`. It must preserve child exit codes, stop on required failure, and fail when an enabled test selection collects zero tests.
8. Ensure entrypoints import without constructing provider/database clients; test this with network/socket guards or patched constructors.
9. Run each narrow tier and then `fast`; record exact outputs and fix only Phase 1-owned failures.
10. Append commands, exit codes, sample sanitized logs, negative-test proof, and exclusions to packet evidence.

#### Packet 4 acceptance checks

- All settings are typed, documented, startup-validated, and centralized; repository search finds no unauthorized environment reads.
- Structured log tests prove correlation fields and redaction.
- Mock mode is deterministic, bounded, provenance-marked, and unable to reach OpenAI.
- Ruff, Pyright strict, pytest, ESLint, TypeScript, Vitest, production frontend build, docstring, boundary, Markdown, and Mermaid checks run through hard-failing documented commands.
- Negative fixtures prove docstring, boundary, duplicate-lock/project, zero-test, secret-log, and mock-network checks can fail.
- No provider client is created at import time; all images remain non-root.

#### Packet 4 stop routes

- A required tool cannot run on supported Windows/WSL2 and CI environments: verify an alternative and record the decision; do not silently omit the gate.
- A lint/type exception would weaken a public boundary: stop for design correction rather than adding a broad ignore.

### Packet 5 — CI tiers and documentation foundation

#### Packet 5 preconditions

- Packet 4 exposes passing hard-failing commands.
- Packet 1 target/sign-off records and packet 3 ADRs exist.

#### Packet 5 allowed outputs

- Root `README.md`, `docs/README.md`, required documentation concern directories, C4/development foundations, specific Phase 1 policies/ADRs, domain-document skeletons, and a runbook backlog index.
- GitHub Actions workflows implementing real Phase 1 checks and documenting later expansion.
- Static OpenAPI generation for actual foundation routes and migration-policy validation that is honest when zero application migrations exist.

#### Packet 5 forbidden outputs

- Fake managed staging/AWS/OIDC execution evidence, fake restore/load/security results, complete later-phase runbooks, invented API/schema fields, or domain documents marked verified before implementation.
- CI jobs that pass with zero matching tests, failure-swallowing commands, mutable action references where immutable commit pinning is available, or permanently disabled required Phase 1 gates.

#### Packet 5 ordered actions

1. Create the concise root README and `docs/README.md`. The docs index records owner, status, last-reviewed date, audience, and links for every document; each document links back.
2. Create `docs/architecture/01-system-context.md`, `02-containers.md`, `03-components.md`, and `04-deployment.md` with small synchronized Mermaid diagrams. Local behavior may be current/verified; staging and production are labeled planned.
3. Create development docs for local setup, workspace/import boundaries, quality commands, CI tiers, dependency updates, and phase evidence.
4. Create and link `docs/retrieval/BM25_PROJECTION_CONTRACT.md`, `docs/security/LOCAL_ADMIN_ALERT_CONTRACT.md`, `docs/security/OPENAI_DATA_GOVERNANCE.md`, and `docs/security/SUBPROCESSOR_GOVERNANCE.md`. BM25 resource values remain assumptions; governance packets remain draft until signed.
5. Create accepted/proposed ADRs for the ParadeDB edition/availability, private-service TLS, availability/RTO/RPO triggers, expand-contract migrations, additive API/SSE compatibility, v1 vision limitation/promotion trigger, and Hybrid Pilot release cut. Create `ADR-embedding-model-dimension.md` as an experiment plan only.
6. Create `docs/adr/README.md` with the remaining Section 15 ADR backlog, owner phase, status, decision trigger, and canonical path. Do not author fake conclusions for later phases.
7. Create planned domain skeletons for `CHUNKING_CONTRACT.md`, `ARABIC_NORMALIZATION.md`, `HYBRID_TUNING.md`, and `QUERY_PROFILE_EVAL.md`. Each contains purpose, owning phase, required future evidence, and links; it contains no fabricated implementation or measurement.
8. Create `docs/runbooks/README.md` as the canonical runbook backlog. List every required runbook with owner phase, prerequisites, status, verification requirement, and escalation owner; do not write procedures for systems that do not yet exist.
9. Implement a PR-fast workflow with plan integrity, locked installs, format/lint/types, unit/contract tests, docstring/boundary/docs checks, secret/dependency scans, foundation OpenAPI drift check, migration-policy static check, and frontend production build.
10. Implement merge/main and nightly workflows only for real Phase 1 behavior: Compose validation/build/health, foundation smoke/restart, dependency/image scans, and any enabled test suites. Document later Supabase/RLS/LightRAG/retrieval/load/restore jobs as future tier requirements rather than fake passing jobs.
11. Pin actions and tool versions according to verified primary/security guidance, grant minimum workflow permissions, use no long-lived cloud/database credentials, and fail if an enabled integration test selection collects zero tests.
12. Validate workflow syntax locally where tooling permits, run the same command tiers, check all Markdown links and Mermaid renders, and append evidence.

#### Packet 5 acceptance checks

- Root and docs indexes are concise, reciprocal, and complete; all documents have owner/status/last-reviewed metadata.
- Four C4 documents contain readable Mermaid source and make current versus planned topology explicit.
- Every Done-gate artifact has one canonical path; no duplicate policy or contradictory ADR exists.
- Required accepted decisions name approver/date; governance and later-phase content are honestly draft/planned.
- PR workflow runs the split-plan integrity verifier and every available hard fast gate without failure swallowing.
- Main/nightly execute at least one real Phase 1 test when enabled and do not claim later-phase integration.
- OpenAPI check reflects only actual foundation routes; migration check explicitly supports zero Phase 1 application migrations without claiming reset/RLS proof.
- Workflow permissions, action pins, secret handling, caches, artifacts, and timeouts are explicit and least privilege.

#### Packet 5 stop routes

- An ADR required for a current security omission is unapproved: keep the dependent configuration blocked.
- A doc/render/action tool cannot be pinned or verified: report it and leave the relevant gate incomplete.
- CI cannot execute because repository hosting is unavailable: validate locally, mark remote execution unverified, and do not claim the workflow passed.

### Packet 6 — one-command startup and Phase 1 exit proof

#### Packet 6 preconditions

- Packets 1–5 have complete evidence and no unresolved launch-blocking stop condition.
- Required local tools/resources meet the documented Windows/WSL2 minimum or the packet reports a blocker.

#### Packet 6 allowed outputs

- Final start/stop/reset and local verification scripts, corrections to Phase 1-owned configuration/tests/docs, and the completed Phase 1 evidence record.
- Checkbox/status changes only after every check passes and the user accepts the exit record.

#### Packet 6 forbidden outputs

- Phase 2 schema/Auth/RLS, Phase 3 ingestion, Phase 4 retrieval, Phase 5 graph, Phase 6 agent behavior, production UI, managed cloud, or compensating fake tests.
- Phase completion based on code presence, a Compose parse, or process liveness alone.

#### Packet 6 ordered actions

1. Restate every `Done when` clause and map it to a command or signed document before execution.
2. From a clean supported workstation state, run the single documented `.\scripts\dev.ps1` command. It must start the pinned local Supabase foundation plus backend, worker, frontend, private ParadeDB, split Valkey, and deny-by-default crawl proxy in mock-model mode without AWS or OpenAI credentials.
3. Run a separate verification script that checks published endpoints, dependency-aware readiness, ParadeDB extension health, both authenticated Valkey policies, private-port absence, proxy denial, non-root users, and mock-model network denial.
4. Run `python scripts/check.py --tier fast`, locked package checks, production frontend build, Docker/Compose validation, and all Phase 1 documentation/CI-policy checks.
5. Intentionally demonstrate at least one representative negative gate in isolation and restore the clean tree afterward; do not leave a failing fixture enabled.
6. Stop with `.\scripts\stop.ps1` and prove persistent volumes remain. Test destructive reset only with disposable data and explicit confirmation.
7. Complete the evidence record with environment/tool versions, exact commands/exit codes, service/port inventory, signed decisions, test/build results, measured startup duration where useful, unverified remote/managed items, deviations, and rollback notes.
8. Run the split-plan integrity verifier and all Markdown/lint checks after the final documentation update.
9. Request explicit user acceptance. Only after acceptance may packet 6 and `status: complete` be set; do not begin Phase 2 in the same run.

#### Packet 6 acceptance checks

- One documented command starts every required local foundation service and all dependency-aware health checks pass.
- No AWS account, AWS credential, live OpenAI key, public ParadeDB/Valkey/proxy port, root application container, or unpinned image is required.
- Locked installs/builds, boundary/docstring/config/logging/mock-network tests, strict lint/types/tests, docs links/Mermaid, frontend production build, and plan integrity pass.
- Signed target/ADR records and every named documentation artifact are linked from `docs/README.md`.
- Exit evidence distinguishes local verified behavior from remote CI, managed, and later-phase unverified work.
- The user accepts the exit record before any completion/status change.

#### Packet 6 stop routes

- Any required service, sign-off, hard gate, immutable pin, or dependency-aware health check remains unavailable after bounded repair: stop with exact evidence and leave the phase pending.
- A later-phase implementation appears necessary to make Phase 1 green: narrow the Phase 1 proof to its honest foundation contract or amend the plan; do not implement ahead.

## Cross-packet invariants

- Preserve the global security, canonical-evidence, durable-state, bounded-work, idempotency, and safe-degradation rules even when Phase 1 has no business logic.
- Preserve the exact package/import names and dependency directions; a new package or reversed edge requires an ADR and plan amendment.
- Treat `prev_review/` as requirements evidence only. Never copy its historical project names, agents, uploads, Airtable/GAS integration, dependencies, commands, or completion claims.
- Use one root lockfile per ecosystem and one LangGraph project. CI and tests must detect duplicates recursively.
- Keep ParadeDB and both Valkey instances private and authenticated; keep crawl egress deny-by-default; keep all durable authority out of Valkey.
- Never instantiate provider/database clients at import time, log secrets/private source text, or require live provider credentials for fast tests.
- Every enabled CI job executes a real check and fails on zero tests. Future tiers are documented, not represented by green no-op jobs.
- Planned later-phase files use `planned`/`draft` status and owner phase; no placeholder is presented as implemented or verified.
- Append a reproducible evidence handoff after each packet. The phase remains pending until packet 6 evidence is accepted.

## Phase sequence requirement

Phase 1 initializes the repository, scaffolds the Section 3 uv/pnpm workspace and import boundaries, configuration, WSL2/local Compose including private digest-pinned ParadeDB plus split Valkey/crawl proxy, documents ParadeDB Community/Enterprise licensing/availability and same-host TLS decisions before omission, establishes tiered CI and the C4/risk foundation, and obtains sign-off on quality/cost/capacity/RTO/availability-trigger targets.

## Stop conditions

Stop this phase and report the blocker instead of improvising when:

- a prerequisite phase or required sign-off is incomplete;
- the actual repository contradicts the plan and the difference changes security, data, cost, or acceptance semantics;
- a required dependency contract cannot be verified from its pinned version and primary documentation;
- an authorization, idempotency, deadline, budget, provenance, or fallback test cannot exercise the real boundary;
- a required integration is unavailable and only a fake or skipped test would pass;
- any launch-blocking check fails after bounded repair attempts.

## Required exit record

Create or update the phase evidence document specified by the repository documentation index with:

- plan requirement and work-packet number;
- files, migrations, APIs, environment variables, and documentation changed;
- exact verification commands discovered from the repository;
- test/build/lint/type/migration results and relevant measured metrics;
- authorization, failure, idempotency, fallback, and bounded-resource evidence;
- unverified external assumptions or unavailable managed-environment checks;
- deviations, ADR approval, and rollback notes;
- explicit handoff inputs and open blockers for the next phase.

Do not set `status: complete` until every `Done when` item below is proven.

## Canonical detailed requirements

The following requirements are redistributed from the original comprehensive plan. They remain normative. Legacy section numbers are preserved so cross-references still resolve through the [section map](../hybrid-graph-rag_ab5281ef.plan.md#legacy-section-map).

## 3. Greenfield monorepo and engineering foundation

Create a uv and pnpm monorepo with explicit deployable boundaries:

- [`pyproject.toml`](../../../pyproject.toml), [`uv.lock`](../../../uv.lock), [`package.json`](../../../package.json), and [`pnpm-workspace.yaml`](../../../pnpm-workspace.yaml) pin reproducible Python and Node dependencies.
- [`apps/agents/`](../../../apps/agents/) contains query and ingestion LangGraph definitions, typed states, prompts, and nodes.
- [`apps/backend/`](../../../apps/backend/) contains the FastAPI transport layer, auth dependencies, routers, response models, streaming, and lifecycle wiring.
- [`apps/worker/`](../../../apps/worker/) claims durable ingestion and LightRAG indexing/deletion jobs and invokes the ingestion graph.
- [`packages/core/`](../../../packages/core/) contains role/ownership-aware domain models, repositories, OpenAI gateway, parsers, custom hybrid retrieval, strict `Bm25Retriever` and `GraphRetriever` interfaces with ParadeDB and LightRAG adapters, tool registry, cost accounting, and shared settings. This package is justified because all three Python deployables use it.
- [`apps/frontend/`](../../../apps/frontend/) is scaffolded as a Next.js App Router workspace in Phase 1, receives the thin developer UI in Phase 6, and receives the approved Stitch/fallback production UX in Phase 8.
- [`supabase/migrations/`](../../../supabase/migrations/) owns schema history and RLS; no custom script replays every migration.
- [`infra/ec2/`](../../../infra/ec2/) and [`docker-compose.prod.yml`](../../../docker-compose.prod.yml) own the single-host deployment.
- [`tests/`](../../../tests/) separates unit, integration, security, contract, end-to-end, load, and evaluation suites.

Follow the deployable-separation pattern from [`prev_review/MONOREPO_RESTRUCTURE_PLAN.md`](../../../prev_review/MONOREPO_RESTRUCTURE_PLAN.md), adapted to this greenfield RAG domain. Do not copy its PO/image agents, Airtable/GAS integrations, local `uploads/`, or old service-client placement. The target layout is:

```text
Demo_Project_3/
├── pyproject.toml                       # uv workspace/tool configuration only
├── uv.lock                              # one committed Python lockfile
├── package.json                         # root Node scripts/tooling
├── pnpm-workspace.yaml
├── pnpm-lock.yaml                       # one committed Node lockfile
├── docker-compose.yml                   # local app + private ParadeDB stack
├── docker-compose.prod.yml              # final EC2 application stack
├── .env.example
├── apps/
│   ├── agents/                          # one LangGraph workspace/deployable boundary
│   │   ├── pyproject.toml
│   │   ├── langgraph.json               # registers query + ingestion graphs
│   │   ├── Dockerfile                   # real Studio/contract image; no placeholder
│   │   └── src/smart_rag_agents/
│   │       ├── query/                    # graph.py, state, nodes, routing
│   │       ├── ingestion/                # graph.py, state, orchestration nodes
│   │       └── prompts/                  # versioned prompt definitions
│   ├── backend/                         # FastAPI HTTP/SSE boundary
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/smart_rag_api/
│   │       ├── main.py
│   │       ├── routers/
│   │       ├── dependencies/
│   │       ├── middleware/
│   │       ├── services/                 # request/auth-scoped application orchestration
│   │       └── schemas/
│   ├── worker/                          # durable queue consumer/process boundary
│   │   ├── pyproject.toml
│   │   ├── Dockerfile
│   │   └── src/smart_rag_worker/
│   │       ├── main.py
│   │       ├── job_runner.py
│   │       └── lifecycle.py
│   └── frontend/                        # Next.js/Vercel workspace member
│       ├── package.json
│       ├── next.config.ts
│       └── src/
│           ├── app/
│           ├── components/
│           ├── features/
│           ├── lib/
│           └── types/
├── packages/
│   └── core/                            # shared application/domain package
│       ├── pyproject.toml
│       └── src/smart_rag_core/
│           ├── domain/
│           ├── settings/
│           ├── repositories/
│           ├── gateways/
│           ├── ingestion/                # parsers/OCR/crawl/chunk/table/sandbox helpers
│           ├── retrieval/
│           ├── tools/
│           ├── security/
│           └── observability/
├── supabase/
│   ├── config.toml
│   ├── migrations/
│   ├── seed.sql
│   └── tests/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   ├── contract/
│   ├── e2e/
│   ├── load/
│   ├── evaluation/
│   └── fixtures/
├── infra/
│   ├── ec2/
│   ├── caddy/
│   ├── paradedb/                        # pinned image/config/versioned derived-index DDL
│   └── aws/
├── scripts/
└── docs/
    ├── architecture/
    ├── security/
    ├── evaluation/
    ├── frontend/
    └── runbooks/
```

Workspace and dependency rules:

- Root `pyproject.toml` is a non-distributable workspace project (`smart-rag-workspace`, `[tool.uv] package=false`) whose member list contains exactly `apps/agents`, `apps/backend`, `apps/worker`, and `packages/core`; each member has its own package metadata while the repository keeps one `uv.lock`.
- The pnpm workspace contains `apps/frontend` and root tooling with one `pnpm-lock.yaml`; do not install a second frontend lockfile.
- Declare direct workspace dependencies by distribution name, never path shorthand or transitive visibility: `smart-rag-agents -> smart-rag-core`, `smart-rag-backend -> smart-rag-agents + smart-rag-core`, and `smart-rag-worker -> smart-rag-agents + smart-rag-core`. `smart-rag-core` imports no `apps/*`; frontend uses HTTP/Supabase only. Referencing members list those exact names in `dependencies`, and root `[tool.uv.sources]` uses matching keys such as `smart-rag-agents = { workspace = true }` and `smart-rag-core = { workspace = true }`.
- `apps/agents/langgraph.json` is the single LangGraph project file and registers both graphs. FastAPI code never lives under `apps/agents`; queue claiming and worker process lifecycle never live under FastAPI.
- FastAPI and worker may invoke graphs in-process for v1. A later LangGraph Server split replaces those import edges with SDK/HTTP adapters without moving graph source directories.
- `packages/core/ingestion` owns parser/OCR/crawl adapters, chunk/table utilities, sandbox launching, and idempotent write helpers with no LangGraph dependency. `apps/agents/.../ingestion` owns only StateGraph state/routing/nodes that orchestrate those helpers; queue polling/claim/lease/heartbeat/release remain in `apps/worker`.
- Shared domain logic, repositories, provider gateways, retrieval, ParadeDB/LightRAG adapters, registry/catalog logic, tools, security, and accounting live in `packages/core`; HTTP schemas/wiring and request/auth-scoped services remain backend-owned, graph state/node wrappers remain agents-owned, and worker lifecycle remains worker-owned. Routers call backend services, which call core repositories/gateways or an agent graph.
- Frontend communicates through FastAPI/Supabase network contracts and never imports Python workspace packages.
- Original files and generated table artifacts live in Supabase Storage, never an `apps/backend/uploads/` runtime directory.
- Add import-boundary tests that fail on reverse dependencies, FastAPI imports in core/agents, LangGraph node definitions in core, queue claim/lease SQL in agents/backend, worker lifecycle in backend, direct ParadeDB/LightRAG use outside their core adapters, or a second `langgraph.json`/lockfile.
- A new top-level app/package or dependency-direction change requires an ADR and plan update; do not create speculative `shared`, `common`, or `utils` packages.

Python package/runtime contract:

- Use distribution/import pairs `smart-rag-core`/`smart_rag_core`, `smart-rag-agents`/`smart_rag_agents`, `smart-rag-backend`/`smart_rag_api`, and `smart-rag-worker`/`smart_rag_worker`. Each member uses pinned Hatchling with a `src/` wheel target containing only its import package.
- Backend starts as `uvicorn smart_rag_api.main:app`; worker exposes a project script whose callable is `smart_rag_worker.main:main`. Neither entrypoint constructs provider clients at import time.
- Following the current LangGraph config contract, `apps/agents/langgraph.json` uses `dependencies: ["."]` and maps graph IDs to `./src/smart_rag_agents/query/graph.py:graph` and `./src/smart_rag_agents/ingestion/graph.py:graph`. Qualification runs `langgraph dev`/config loading from `apps/agents`.
- Build every Python image with the repository root as Docker context. Copy root workspace metadata plus every member `pyproject.toml` for resolution; install third-party dependencies in a cacheable layer, then copy only the source trees required by the selected package and its direct/transitive workspace dependencies.
- Final image sync uses `uv sync --locked --package <distribution-name> --no-dev`; `--locked` must fail when metadata and `uv.lock` disagree. Backend copies core + agents + backend sources, worker copies core + agents + worker, and the agents contract image copies core + agents. Images never regenerate or carry a private lockfile.

Add strict configuration and quality controls from day one:

- Pydantic Settings per deployable, validated at startup; no scattered `os.getenv` calls.
- Ruff formatting/linting, Pyright strict type checking, pytest, pre-commit, ESLint, TypeScript strict mode, Vitest, and Playwright.
- Exact lockfiles, non-root containers, health checks, structured JSON logs, request/run IDs, generic client errors, and no failure-swallowing CI commands.
- Node docstrings state inputs, outputs, side effects, retries, idempotency, and failure mode.

## 15. Documentation and handoff

> **Phase 1 ownership note:** Establish the documentation structure, enforcement, metadata, C4 skeleton, required ADR/runbook backlog, and initial policy drafts. Later phases fill in and verify the domain-specific API, migration, retention, provider, deployment, and operational content when those behaviors exist; Phase 11 completes the production handoff. Do not invent final operational evidence in Phase 1.

Create C4-aligned documentation rather than repeating the prior documentation drift:

- Treat documentation as a required deliverable in every implementation change. Every authored Python module, class, function, async function, and method has a Google-style docstring; generated/vendor code is the only explicit exclusion. Public/exported TypeScript functions, hooks, components, server actions, and non-obvious types use TSDoc/JSDoc.
- Function documentation covers purpose, parameters, return/yield, exceptions, side effects, authorization, idempotency, retry/timeout, units/provenance, and examples where relevant. LangGraph nodes additionally document state input/output, durable writes, external/model calls, budgets/deadlines, and failure/fallback routing.
- Keep root [`README.md`](../../../README.md) as a concise onboarding/index page. Maintain [`docs/README.md`](../../../docs/README.md) as the full documentation map with owner, status, last-reviewed date, and reciprocal links.
- Split detailed documentation by audience and concern under `docs/architecture`, `development`, `api`, `ingestion`, `retrieval`, `graph`, `agent`, `frontend`, `security`, `evaluation`, `deployment`, `runbooks`, and `adr`. Use one primary topic per Markdown file and split files that mix concerns or grow beyond roughly 300 lines.
- Architecture, component, trust-boundary, data-flow, authentication, ingestion, retrieval, agent-routing, state-machine, deployment, database, and operational-workflow documents contain Mermaid source diagrams. Use `flowchart`, `sequenceDiagram`, `stateDiagram-v2`, or `erDiagram` as appropriate; diagrams supplement rather than replace detailed prose.
- Keep Mermaid diagrams small enough to review, split dense views by concern, use stable descriptive IDs and quoted labels, avoid hard-coded styling/colors, and update diagrams in the same change as the represented flow or schema.
- Every document includes applicable prerequisites, contracts, data flow, limits, security implications, failure/degraded behavior, examples, verification commands, troubleshooting, and links to canonical code/schema/API sources. Planned or externally unverified content is labeled explicitly.
- Document every public API, environment variable, migration, queue/job/state machine, provider integration, prompt/model policy, configuration default, deployment change, and user-visible workflow in the same change that introduces or changes it. Prefer links to one canonical explanation over copied sections.
- [`docs/architecture/01-system-context.md`](../../../docs/architecture/01-system-context.md): actors, external systems, and trust boundaries.
- [`docs/architecture/02-containers.md`](../../../docs/architecture/02-containers.md): Vercel, EC2/ParadeDB services, Supabase, OpenAI, LangSmith, and SES.
- [`docs/architecture/03-components.md`](../../../docs/architecture/03-components.md): backend, worker, graphs, BM25 projection/retrieval, retrieval fusion, and registry components.
- [`docs/architecture/04-deployment.md`](../../../docs/architecture/04-deployment.md): local, staging, and production nodes/ports/state.
- [`docs/ingestion/CHUNKING_CONTRACT.md`](../../../docs/ingestion/CHUNKING_CONTRACT.md): typed elements, format cleaning, size/overlap/atomic-unit rules, parent reconstruction, deduplication, provenance, versions, and acceptance fixtures.
- [`docs/retrieval/ARABIC_NORMALIZATION.md`](../../../docs/retrieval/ARABIC_NORMALIZATION.md): raw-versus-search text, exact normalization mappings/version, canonical Supabase field plus ParadeDB projection/query parity, limitations, and BM25 ablations.
- [`docs/retrieval/HYBRID_TUNING.md`](../../../docs/retrieval/HYBRID_TUNING.md): immutable configuration profiles, candidate/rerank/MMR/RRF/coverage search space, per-query-class curves, selected values, and rollback.
- [`docs/evaluation/QUERY_PROFILE_EVAL.md`](../../../docs/evaluation/QUERY_PROFILE_EVAL.md): field labels/metrics/confidences, failure attribution, few-shot promotion, split isolation, and signed thresholds.
- ADRs for graph-eligibility/ACL isolation, custom Hybrid plus ParadeDB BM25 plus LightRAG responsibilities, ParadeDB Community/Enterprise licensing and same-host availability/fallback, `PGTableGraphStorage`, canonical/inference grounding, structured-table execution, reserve-once durable budgets, embedding model/dimension/index memory, database workload isolation/replica consistency, parser shared-kernel acceptance/upgrade triggers, egress enforcement, Valkey/ParadeDB TLS decisions, availability/RTO/RPO/growth triggers, zero-downtime expand/contract migrations, API/SSE compatibility, optional-tool disclosure, fetch streaming, private service-only BM25/LightRAG access, and the vision-captioning promotion trigger. [`docs/security/OPENAI_DATA_GOVERNANCE.md`](../../../docs/security/OPENAI_DATA_GOVERNANCE.md) and [`docs/security/SUBPROCESSOR_GOVERNANCE.md`](../../../docs/security/SUBPROCESSOR_GOVERNANCE.md) form one signed external-processing governance packet; do not duplicate signed decisions as separate ADRs.
- Runbooks for protected migrations/credential rotation, Supabase signing-key/JWKS rollover, ClamAV engine/signature update/staleness/re-scan, Valkey outage/recovery, ParadeDB projection replay/clean rebuild/version switch/fallback, local/in-app admin alerts, origin-secret dual rotation, alert routing, LightRAG workspace upgrades/replacement/reconciliation/deletion/bulk-onboarding ETA, embedding-model parallel rebuild, re-embedding after metadata edits, dead-letter replay, conversation deletion verification, user offboarding/export/deletion, retention/legal hold, audit-chain/anchor verification, alias/feedback curation, key/session rotation, instance rebuild, staging promotion, Supabase database-plus-Storage backup/restore reconciliation, incident response, and rollback.
- OpenAPI and Pydantic field descriptions serve as the canonical API schema; frontend types are generated from it.
- Phase 1 enables Ruff pydocstyle plus an AST-based test for all required Python docstrings, Markdown lint/link validation, Mermaid syntax/render validation, and CI checks that public API/configuration/environment changes include corresponding documentation.

Default retention, configurable only through an owner-approved policy:

- Disable departed users and revoke sessions immediately; remove team access immediately; export on approved request; purge/pseudonymize profile/private conversation data after 30 days unless legal hold applies.
- Undeleted conversations/messages: 90 days after last activity; undeleted run event payloads/checkpoints: 30 days; completed-run idempotency keys: seven days; user feedback: 12 months; aggregated usage: 24 months; LangSmith traces: 30 days with payload redaction; audit events: seven years in write-once export. User-requested conversation deletion follows the [legacy Section 10 privacy contract in Phase 6](./06-phase-agent-intelligence.md#10-fastapi-contract-streaming-and-security) immediately and does not wait for these windows.
- Document deletion excludes retrieval immediately; primary objects/derived indexes are targeted for purge within 24 hours, while encrypted provider backups expire under the documented backup schedule.

Handoff reserves one to two engineer-days per quarter for LightRAG dependency/schema qualification, deletion drill, and source-map health review. The owner receives the engine exit criteria, current pin, workspace version, measured graph survival, known deletion limitations, and a tested disable-to-Hybrid-only procedure.

The handoff dashboard/runbook keeps the Section 1 availability and Section 4 database-isolation triggers visible with a named owner. Crossing a trigger creates a dated architecture-review action rather than merely raising an alarm; the review records whether to resize, isolate reads/LightRAG, or start the multi-host design.

## 13. CI, tests, and no-go gates

> **Phase 1 CI ownership:** Define the hard tier structure and wire the checks available in the greenfield skeleton, including the split-plan integrity verifier. Phase 9 owns the exact local release-candidate suite. Phase 10 owns managed release/staging IaC, OIDC, CDN, KMS/S3, restore, and topology proof. Phase 1 must not provision or fake managed evidence.

GitHub Actions use hard gates with no `|| true` fallbacks, tiered so developers are not pushed to bypass a monolithic pipeline:

Phase 1 documents and statically guards the future managed migration/deployment contract: GitHub OIDC, no long-lived AWS/database credential, protected immutable migration artifacts, and environment separation. Phase 10 implements and executes that workflow against managed staging.

- Per PR: split-plan integrity verification, Python/Node format, lint, strict types, unit/component tests, generated OpenAPI contract, migration static checks, secret/dependency scans, and production frontend build.
- Merge queue/main: migration reset/reapply, RLS/security integration, local Supabase/pgvector/ParadeDB BM25/LightRAG/Valkey integration, parser sandbox, Docker builds/health, and targeted Playwright smoke tests.
- Nightly: full Playwright, retrieval/routing/injection evaluation with frozen fixtures, dependency/Trivy scans, backup/restart tests, and cost-capped opt-in live-model evaluation.
- Phase 9 local release candidate: local load/deadline/connection-pool/security/evaluation/restore and exact-image gates.
- Phase 10 managed staging: IaC/OIDC/CDN/KMS/managed restore/topology gates. Every integration job in every tier fails if zero matching tests execute.

## Phase deliver, review, and done gate

### Phase 1 — Foundation

- Deliver: the exact Section 3 repository structure, one Python/Node lockfile each, workspace package metadata, single `langgraph.json`, real Dockerfiles, import-boundary/docstring/documentation checks, WSL2/local Compose helpers with digest-pinned private ParadeDB plus split Valkey/crawl proxy, BM25 and Valkey same-host TLS/licensing/availability ADRs before omissions, mock-LLM mode, health endpoints, tiered CI, `docs/README.md` plus split architecture/development documentation, quality targets, embedding ADR experiment plan, effort/risk register, availability/isolation triggers, normal-versus-maintenance cost sign-off, signed v1 media/timezone choices, dated Hybrid Pilot decision checkpoints, expand/contract plus API/SSE compatibility ADRs, local-admin-alert contract, and OpenAI/subprocessor governance packet drafts.
- Review: targets, expected corpus/concurrency, BM25 index/rebuild resource assumptions, ParadeDB Community versus Enterprise and derived-index fallback, normal monthly/daily spend versus the potentially larger graph-maintenance reserve, RTO/RPO/growth triggers, v1 figures/charts limitation and temporal anchor, Hybrid Pilot decision dates/criteria/approver, package boundaries, local resources, ParadeDB/Valkey TLS/credential/network decisions, migration/API compatibility, governance scope, and security defaults.
- Done when: signed quality/cost/capacity/RTO/RPO and availability/isolation targets exist, with the BM25 projection/rebuild assumptions, distinct normal and graph-maintenance budgets, the signed media/timezone policy, and dated end-of-Phase-1/end-of-Phase-4 Hybrid Pilot decision criteria; the exact workspace, dependency directions, package metadata, root lockfiles, single `langgraph.json`, and real non-root Dockerfiles pass boundary/build checks; ParadeDB/Valkey same-host TLS and ParadeDB licensing/availability ADRs are linked before Compose omissions; one documented command starts healthy local backend/worker/frontend, private ParadeDB, split Valkey, crawl-proxy, and local-Supabase-facing skeleton services in mock-LLM mode with no AWS account; tiered fast CI plus import, docstring, Markdown/link/Mermaid, strict type, lint, test, production-build, and migration-policy static gates execute without failure swallowing; and `docs/README.md`, the split architecture/development skeleton, `QUALITY_TARGETS.md`, embedding and vision-trigger ADR plans, BM25 topology/rebuild/fallback contract, expand/contract and API/SSE compatibility policies, effort/risk and Hybrid Pilot decision records, local-admin-alert contract, availability/isolation triggers, and both governance packet drafts are present, linked, and reviewed.
