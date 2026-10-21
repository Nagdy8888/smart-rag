# Infrastructure and deployment review

See [scope and evidence conventions](README.md). Verdict: **intentional local security topology and protected deployment wiring; end-to-end operational evidence remains incomplete**.

## Positive design choices

`docker-compose.yml` keeps ParadeDB and Valkey on a private internal network without published host ports. Limits and cache are separate Valkey instances with different memory/eviction policies. Crawl egress has a dedicated proxy. Image references use immutable digests in important places. The parser launcher is designed for no-network constrained execution, and production API/worker images are intended to be non-root/distroless.

GitHub workflows use minimal declared permissions and pinned action SHAs. Preflight includes Gitleaks, plan integrity, Python dependency audit, and Node audit. Staging deployment uses GitHub OIDC and a protected environment rather than a long-lived AWS access key in the workflow.

These are source/configuration observations. Actual host firewall rules, container permissions, secret distribution, cloud environments, branch protection, and image provenance were not inspected live.

## OP-01 — P2: staging workflow submits a deployment command without observing completion

**Evidence: confirmed workflow.** `.github/workflows/staging-deploy.yml` configures OIDC and ends with `aws ssm send-command` for `SmartRagStagingDeploy`. No subsequent wait/get-command-invocation, rollout health check, or rollback-result verification appears in that workflow.

**Impact:** workflow success demonstrates that SSM accepted the command, not that the remote deployment finished successfully. The remote SSM document may contain additional checks, but its actual execution was not inspected. Operators can mistake dispatch success for deployed readiness.

**Recommendation:** retain the returned command ID, wait for the intended instance's invocation to finish within a bounded timeout, fail on remote errors, and check public API/handshake plus an authorized representative journey. Archive sanitized image/commit and deployment outcome. If remote orchestration already supplies this, make that evidence explicit in the workflow result.

**Acceptance:** a remote deployment failure or unhealthy new API makes the workflow fail; a green deployment includes the exact image and successful readiness/journey evidence.

## OP-02 — P2: quick-start documentation disagrees with the current frontend topology

**Evidence: confirmed source mismatch.** README Quick start lists the console at `http://localhost:3000` and describes starting Compose through development scripts. Current `docker-compose.yml` explicitly says the browser UI is the Vercel project and publishes only the API app port.

**Impact:** a new operator can expect a local console that this Compose topology does not itself provide. Build-time `NEXT_PUBLIC_API_BASE_URL` also makes local/hosted wiring easy to misinterpret: a loopback API origin works only for a browser on that same machine.

**Recommendation:** document the supported paths separately: local API plus hosted console, or an explicitly started local Next.js console. State which browser can reach the configured API, where public values are set, and that changing public values requires a frontend rebuild/redeployment.

**Acceptance:** a fresh setup follows one path without a dead localhost URL or an inaccessible loopback backend. Verify the exact `apps/frontend` deployment root and build-time configuration on the intended host.

## Scaling and availability

BE-02 must be addressed before multiple API executor processes/replicas are enabled. Durable events support replay, but process-local start flags do not supply cross-process ownership. Document the current replica/process constraint until an exclusive durable claim is proved.

BE-01 creates a long-lived memory/retention risk. BE-03 and SEC-02 make source previews disproportionately expensive and potentially dangerous inside API processes. Network and CPU isolation must cover preview/figure work as well as the original parser.

Warmup and readiness are thoughtfully separated. A failed warmup is recorded and readiness reports query runtime health; do not replace that with a liveness-only load-balancer gate. Conversely, decide which derived services are optional/degraded so a graph outage does not unnecessarily disable safe Hybrid queries.

## Database and connection capacity

The code uses transaction-pooler API traffic alongside session/direct requirements for checkpointers and LightRAG. Several preview services also open fresh connections. No actual hosted connection limit or peak pool occupancy was measured.

Before scaling, inventory maximum sessions per API/worker replica and adapter, then prove the total stays within the chosen tier budget with operational headroom. Exercise timeout, pool exhaustion, and recovery. Keep schema-admin credentials separate from runtime roles and avoid interpreting `SET ROLE` in code as proof that deployed login-role grants are least privilege.

## CI and dependency policy

PR fast/nightly call format, lint, types, unit, contract, frontend/docs, and migration checks. Main also runs Compose checks. Workflow comments identify additional live/nightly work as future. Comments are not a substitute for checking what is actually enforced, and passing static checks cannot establish backup restoration or live RLS.

The local checkout already fails deterministic gates. Resolve QA-01 before using a successful build or image publication as readiness evidence. Existing dependency exceptions need expiration/ownership; the Node high-threshold audit currently exits zero despite an ignored high advisory and moderate/low findings.

## Operational proof still needed

- Migration upgrade and least-privilege/RLS tests on an isolated hosted test target.
- Backup restoration with canonical data, private objects, graph/BM25 reconstruction, and conversation state.
- Worker crash/reclaim and budget orphan reconciliation.
- Rolling API restart during active SSE, reconnect, and cancellation.
- Degraded Valkey/Postgres enforcement behavior and alerting.
- Actual crawl/provider/parser egress enforcement.
- Health/readiness and authorized public journeys after deployment.
- External trace deletion, audit chain/anchor verification, and retention checks.

These items are verification gaps, not claims of observed outages. No deployment, cloud mutation, migration, or remote publication was performed for this review.
