# Security review

See [scope and evidence conventions](README.md). This is a code-based security assessment with selected local checks, **not a penetration test, compliance certification, or proof of deployed security**. No production exploit or cross-user data disclosure was established.

## Trust boundaries and positive controls

The important boundaries are browser-to-API identity, server-to-database authority, canonical-to-derived search, uploaded bytes-to-parser, corpus-to-model provider, model output-to-answer release, and privileged Storage/Auth Admin modules.

Controls inspected include:

- ES256/RS256 JWT allow-list, issuer/audience/expiry verification, unknown-key refresh, and rejection of symmetric/service-role/anonymous tokens.
- Current profile, disabled-user, and session-revocation checks.
- Server-derived roles and authorization versions; production test headers rejected.
- Parameterized database calls and canonical candidate reauthorization.
- Private derived search and storage; no need to return privileged storage URLs to the browser.
- Body-size limits, generic errors, exact-origin CSP connections, restrictive API headers, and no-store responses.
- Dedicated crawl proxy, URL/scheme/port/scope checks, DNS/IP validation, redirect validation, and provenance.
- A process-isolated typed table executor with secret-stripped environment, verified artifact hash/path, parameterized plans, and external-access disabling after authorized artifact load.

Selected contracts returned 42 passes and 11 skips. In-memory/static tests and mocks do not establish the actual hosted RLS, grants, queue isolation, or network enforcement.

## SEC-01 — P1: figure vision bypasses provider governance and durable spend controls

**Evidence: confirmed code.** `ingestion/index_graph.py:582` materializes/describes figures before `load_external_processing_input` at line 622 and before canonical replay checks at lines 678/726. `ingestion/figures/describe.py:15` only needs mock mode and an API key; it receives no provider approval, current policy decision, budget reservation, or durable operation identity. `gateways/openai_figure.py:66-93` directly creates the provider client, sends PNG content, and returns text without recording response usage.

The ordinary external-processing policy explicitly denies real-company processing when provider settings are unverified. The vision path does not invoke that decision. Earlier scan/extraction checks do exist; the finding is that those are not the complete external-provider authorization/accounting gate.

**Impact:** in live mode with a configured key and eligible figures, company images can be sent despite an external-provider decision that would block other processing. Up to 40 calls per document can also occur outside durable usage accounting. A retry can repeat vision work before reaching the completed-operation replay check. No actual unauthorized external transfer was performed in this review.

**Recommendation:** make figure vision use the same external-processing decision and job-level counted provider wrapper as other external processing. Check replay before provider work, record a stable artifact/attempt identity, and capture actual usage and timeout-after-send outcomes. `store=False`, timeouts, and output caps are useful but do not replace authorization or accounting.

**Acceptance:** provider-settings-unverified, denied-category, missing attestation, exhausted budget, replay, crash, and retry scenarios make no unauthorized or duplicate provider send.

## SEC-02 — P1: PDF processing escapes the no-network parser boundary

**Evidence: confirmed code.** `ingestion/figures/materialize.py:64` opens the PDF in the main worker; `_crop` calls `get_pixmap` at line 162. `services/citation_page_http.py:104` renders inside the API through `parser/page_image.py`. These paths do not use `parser/sandbox/launcher.py`.

Figure crop PNG size is checked after extraction/rendering, and the crop path has no equivalent pre-render pixel cap to the preview renderer. Preview rendering does cap pixels and final bytes, but runs in a process that has application privileges.

**Impact:** malformed or pathological PDFs reach native parsing in credential-bearing processes with different resource/egress privileges from the intended sandbox. Malware scanning is valuable but does not prove a PDF cannot exploit a parser or exhaust resources. No parser vulnerability was exploited here.

**Recommendation:** render/crop in a no-network, credential-free constrained process/container with CPU, memory, pixel, byte, and wall-time bounds. Return only a validated image/artifact. Consider producing approved page/figure artifacts during ingestion rather than repeatedly opening originals during reads.

**Acceptance:** a hostile-size page, malformed PDF, and a render timeout cannot exhaust or crash the API/worker; the render child cannot see secrets or reach the network.

## SEC-03 — P2: unknown JWT key IDs can force repeated outbound JWKS refreshes

**Evidence: reproduced with a fake key source; no network used.** `security/jwks.py:280` refreshes once per verification when the key is absent, without a global cooldown, negative cache, or refresh single-flight. Ten repeated unknown-key resolutions caused ten refresh calls in the local reproduction. Sensitive mutation pre-auth limits do not protect every GET before JWT verification.

**Impact:** untrusted requests can amplify traffic to Auth and consume sync authentication worker capacity, particularly under concurrent invalid tokens. “One refresh” is bounded per request, not per time window.

**Recommendation:** bound token/header sizes, use refresh single-flight and a short unknown-key/cooldown policy while retaining rollover support, and apply appropriate ingress authentication-failure limits. Test a valid newly rotated key during the cooldown design.

**Acceptance:** concurrent invalid-key bursts cause a bounded number of JWKS fetches while a legitimate rotation remains usable within the specified interval.

## SEC-04 — P2: current dependency advisories require exposure review

**Evidence: live local audits, 20 October 2026.** See `evidence/python-audit.txt`, `node-audit.txt`, and `node-audit.json`.

- Python: `aiohttp 3.14.3` has three nonignored advisory entries; the audit lists `3.14.4` as a fix. One advisory concerns excessive/unbounded CPU or memory use. Treat client/server use and reachability separately. [Advisory](https://github.com/advisories/GHSA-2g87-pp6c-29x5).
- Node: 11 findings, including seven moderate and three low entries, plus one ignored high. Examples include Vitest/mocker below 4.1.11, brace-expansion, markdown-it, js-yaml, smol-toml, DOMPurify, and KaTeX. Some enter documentation/developer tooling rather than the product bundle. The Vitest issue concerns server/mock endpoint exposure; a vulnerable installed version alone is not evidence of an exposed dev server. [Vitest advisory](https://github.com/advisories/GHSA-82fw-gwwq-j7x9).
- Existing root policy ignores `GHSA-vfj7-8cjw-p6xm`, a braces stack-exhaustion advisory. Its continued acceptability was not established by this review. [Ignored advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).

**Recommendation:** update reachable runtime dependencies first, then tooling; attach owner, rationale, exposure, and expiry to each exception. Re-run pinned lockfile checks and the relevant tests. Do not blindly update every package or claim the audit exit code proves a clean dependency tree.

**Acceptance:** each remaining advisory has an explicit current disposition and proof of whether it enters the shipped image, public bundle, or exposed tool process.

## SEC-05 — P2 hardening: production CSP allows inline scripts

**Evidence: accepted implementation tradeoff.** `apps/frontend/next.config.ts` intentionally returns `script-src 'self' 'unsafe-inline'` in production. Production `unsafe-eval` is correctly absent, and connection origins are explicit.

**Impact:** inline-script allowance reduces CSP's protection if an HTML/script injection bug is introduced. This review did not find or exploit an actual script injection vulnerability.

**Recommendation:** assess a per-request nonce design for sensitive authenticated pages, accounting for dynamic rendering and caching. The official framework guidance explains both nonce and non-nonce approaches and their rendering tradeoffs; a static hardcoded nonce is not a fix. [Next.js CSP guidance](https://nextjs.org/docs/app/guides/content-security-policy).

**Acceptance:** a production-browser test blocks injected inline code while framework/auth/navigation scripts still work, or the existing tradeoff is explicitly retained with an owner and reason.

## Answer integrity is also security

AG-01, AG-02, and AG-04 weaken the boundary between untrusted generated text and trusted cited answers. An uploaded instruction or mistaken model response must not become more trustworthy because a formatter runs after verification. Authorization of retrieved chunks and semantic support of the final answer are separate properties; both are needed. This aligns with the RAG-specific threat model of untrusted retrieval, ingestion poisoning, and output validation. [OWASP RAG security guidance](https://cheatsheetseries.owasp.org/cheatsheets/RAG_Security_Cheat_Sheet.html).

## Accepted decisions and residual risks

**MFA removal is intentional.** `docs/adr/ADR-frontend-functional-overhaul.md:19-52` records explicit approval to remove MFA/TOTP/AAL2. Current assurance-independent authorization matches that decision. The local security skill still requires MFA and is stale relative to the accepted ADR. This is governance/documentation drift, not permission to silently restore MFA.

Ordinary authentication leaves privileged accounts more exposed to password/session compromise. Maintain revocation, current role checks, rate limits, destructive confirmations, and audit controls; revisit stronger authentication only through a new product/security decision.

**Privileged secret modules are a code boundary, not a process boundary.** `storage_admin/settings.py` loads a broad Storage credential inside the API process, and worker privilege helpers do the equivalent for worker operations. Typed settings isolation prevents accidental broad propagation, but a process compromise can still access its environment. Avoid describing this as separate-service isolation. A broker or narrower credential strategy would reduce blast radius; no current credential leak was established.

## Unverified security properties

Hosted RLS/grants and SECURITY DEFINER ownership, actual egress enforcement, provider governance configuration, audit anchoring, invitation lifecycle, deletion of external traces, restored backups, session downgrade races, and cross-replica execution require live tests. The selected source checks do not replace those tests.

Crawl code shows layered SSRF defenses; no concrete SSRF bypass was established. Validate the actual connection peer and all redirect/DNS behavior in the deployed proxy, consistent with [OWASP SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html).
