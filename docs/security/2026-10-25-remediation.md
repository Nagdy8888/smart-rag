# Security remediation — 25 October 2026

This implements source changes for the seven validation leads from the review of
commit `6cb0d8beaadcebace6189d0f4235e75286776dd7`. The original audit remains a
historical source snapshot. These changes are local and uncommitted; no deployment
or live database operation was performed. **LangGraph checkpoints are preserved.**

## Changes implemented

1. **Figure provider policy and accounting.** The indexing graph builds its
   external-processing input before figure descriptions. Every description checks
   the existing attestation, category/review, detector, scan, policy-version and
   provider-settings decision. Mock mode never sends. Canonical replay precedes
   image side effects. A leased job operation records an irreversible attempted
   marker and a committed ingestion budget hold before sending. Completed
   descriptions replay from the ledger. An uncertain attempt is never automatically
   sent again. Provider token counts and request IDs are retained separately.
2. **Native figure allocation and containment.** PDF figure cropping now runs
   inside the existing no-network, nonroot parser container. The indexing worker
   consumes size-bounded PNG output without reopening the PDF. Crops require finite
   geometry, page intersection, maximum side length and a four-million-pixel cap
   before allocation. Direct extraction of potentially unbounded original image
   streams was removed. The worker validates PNG signature, header dimensions,
   encoded size and decoded size without invoking a native decoder. Raster payloads
   are stripped before canonical chunk writes. Parser result files have a 128 MiB
   size ceiling; Docker logs and captured stdout/stderr cannot grow in the worker.
3. **Approved crawl redirects.** Every hop checks `ApprovedCrawlScope` before DNS
   resolution and transport. The same scope follows robots fetches. Existing
   public-IP, peer pinning, redirect count and response-size checks remain.
4. **JWKS refresh amplification.** JWT and key-ID lengths are bounded. Concurrent
   misses share one refresh lock and a ten-second cooldown, including failed
   fetches. There is no attacker-keyed miss cache. Trusted cached keys bypass the
   refresh lock. Genuine new keys become usable after the cooldown, while ordinary
   TTL expiry still fails closed if a refresh cannot succeed.
5. **Active stream session invalidation.** Verified token expiry/issue times travel
   in server-derived caller context. Replay checks expiry before each frame and
   reloads current membership/session state at most once per second of active
   delivery. Revocation, disabled/missing profile, changed role or authorization
   version closes delivery. A token without `iat` cannot bypass a profile-wide
   revocation. Test-only injected identities retain their existing explicit bypass.
6. **Origin transport.** Terraform rejects HTTP origin policy. The historical
   `Caddyfile.http443` filename now contains the TLS configuration, and its release
   assertion rejects plaintext listeners. The staging example selects the standard
   Caddyfile. Existing origin-header guards and streaming timeouts remain.
7. **SSM parameter interpretation.** All three documents use `ENV_VAR`
   interpolation, strict value patterns and quoted shell variable expansion.
   Migration hashes require 64 lowercase hexadecimal characters; API image IDs
   require an immutable digest. Raw template interpolation was removed from shell
   text. Agents without environment interpolation fail before work starts.

The ingestion reservation check/insert now shares a transaction-scoped advisory
lock across workers. No schema migration or checkpoint cleanup is part of this fix.

## Budget and recovery behavior

The image operation reserves a conservative USD 0.05 from the existing daily
ingestion budget per unique image operation. This is an admission/accounting hold,
**not a measured invoice charge**. Measured provider token counts are separate.
The hold remains charged after a crash or uncertain send; an operator must
reconcile that outcome rather than release it and silently retry. No existing user,
company or monthly cap was raised. No paid model calls were made during testing.

Denied or unavailable descriptions preserve the image and its caption. An older
parser image does not produce the new raster output: rebuild the parser together
with the worker before enabling the changed ingestion path. Existing stored PDFs,
images, citations and checkpoints were not rewritten or re-ingested.

## Verification

The new offline regression module covers policy denials, durable-before-send
ordering, successful replay, uncertain-send suppression, random-key bursts,
legitimate rollover, fetch failures, trusted-key availability, invalid crop geometry,
off-domain redirect rejection, session lifecycle transitions, midstream revocation,
SSM input patterns and rejection of plaintext origins.

An additional Docker contract uses a synthetic PDF and the rebuilt parser image.
It verifies that figures survive parsing, the worker does not call `fitz.open`, and
transient raster metadata does not survive materialization. It uses no live
database, private corpus or provider request.

Final command results are recorded in the companion
[validation summary](2026-10-25-validation.json). The original 50-case audit plan is
still broader than this focused regression suite; it is not represented as 50/50.

- Full unit suite: **2,242 passed, 4 skipped**. Skips are not counted as passes.
- New security regressions: **40 passed**, included in that unit total.
- Selected offline SSE/crawl/native-PDF contracts: **19 passed**; two live/external
  cases were excluded. The final rebuilt parser image was separately rechecked:
  **1 passed**, overlapping the selected-contract coverage.
- Ruff lint/format, strict Pyright, `git diff --check`, and example Compose
  configuration validation passed.

The parser test image is a source overlay on the existing cached dependency image.
An offline clean build could not fetch Alpine package indexes; it is not reported
as a successful fresh dependency/base-image rebuild. No running service was replaced.

## Remaining deployment evidence

These source fixes do not establish live infrastructure security. Before any later
release, verify effective runtime database roles/grants/RLS and migration parity;
provider settings and egress enforcement; certificate-backed origin HTTPS; the
effective SSM document revision and supported Agent version; protected GitHub
environments and exact artifact/check binding; dependency exceptions; and separate
database/object backups with a disposable restore.

No Terraform apply, AWS SendCommand, hosted Supabase change, credential rotation,
checkpoint deletion, backup deletion or release was performed. Privileged MFA
policy remains the accepted product decision. The production database is still
undecided. This is not production security approval.

## Implementation references

- [AWS environment parameter interpolation](https://docs.aws.amazon.com/systems-manager/latest/userguide/documents-syntax-data-elements-parameters.html)
- [Supabase signing-key discovery and caching](https://supabase.com/docs/guides/auth/signing-keys)
- [PyMuPDF clipping and raster resolution](https://pymupdf.readthedocs.io/en/latest/page.html)
