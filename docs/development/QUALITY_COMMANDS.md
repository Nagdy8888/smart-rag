---
title: Quality commands
owner: engineering-lead
status: draft
last-reviewed: 2026-08-25
audience: engineering
---

# Quality commands

```powershell
uv run python scripts/check.py --tier format
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python scripts/check.py --tier unit
uv run python scripts/check.py --tier contract
uv run python scripts/check.py --tier docs
uv run python scripts/check.py --tier frontend
uv run python scripts/check.py --tier fast
uv run python scripts/ci/check_openapi.py
uv run python scripts/ci/check_migrations.py
uv run python scripts/phase10_staging.py assert-iac
uv run python scripts/ci/check_phase10_packet1.py
uv run python scripts/ci/check_phase10_packet2.py
uv run python scripts/ci/check_phase10_packet3.py
uv run python scripts/ci/check_phase10_packet4.py
uv run python scripts/ci/check_phase10_packet5.py
uv run python scripts/ci/check_phase10_packet6.py
uv run python scripts/ci/check_phase10_packet7.py
```

GitHub CI invokes one `--tier` per job (or a paired reusable job such as
`format-lint` / `docs-frontend`). It does not run `--tier fast` as a single
GitHub job. Local `uv run python scripts/check.py --tier fast` still exists
and still includes `types`. Parallel job membership:
[CI_TIERS.md](./CI_TIERS.md).

When `CI=true`, `check.py` appends `--tb=short -ra` to the unit and
contract pytest invocations. Local runs without that environment variable
keep pytest’s default traceback style.

The ordinary contract and fast tiers may skip live integration checks when
hosted or ParadeDB prerequisites are unavailable, which keeps dependency-only
CI deterministic. DB-backed schema/RLS suites are opt-in via explicit
`SUPABASE_DB_URL` (they refuse hosted `*.supabase.co`).

Phase 9 local release-candidate CLI was retired. Compact Packet 1 scan
status remains historical in
`docs/deployment/phase-09/candidate-scan-summary.json`.

Tiers hard-fail (no `|| true`). Zero collected tests fail the unit/contract tiers.
The `lint` tier runs Ruff with pydocstyle (D) enabled; missing Google-style
docstrings fail lint. The `types` tier stays in `FAST_TIERS` and still invokes
`python -m pyright` strict over `apps/`, `packages/core`, `scripts`, `tests`,
and `infra/crawl-proxy` (`pyproject.toml` `[tool.pyright]`). Packet-scoped
“zero new errors” is not a pass. Full-repo Pyright is **0** errors as of
2026-08-16 (exit 0). The same tier also runs
`scripts/ci/check_pyright_baseline.py`, which fails if the count
**increases** above the recorded baseline of 0. The ratchet is not a
waiver. See [PYRIGHT_BASELINE.md](./PYRIGHT_BASELINE.md).

```powershell
uv run python scripts/ci/check_pyright_baseline.py
```

The frontend tier runs `next typegen` before standalone `tsc --noEmit`, so
route-aware `PageProps` and `LayoutProps` are available on a clean checkout.
Markdown checks cover maintained documentation. Preserved historical reviews in
`docs/prev_review/` and generated Stitch source exports in
`docs/stitch_smart_rag_enterprise_console/` are explicitly excluded and must
not be cited as current implementation evidence.

Dependency and secret scans use the locked Python/Node graphs and the same Gitleaks version as PR CI:

```powershell
uv export --frozen --all-packages --group dev --no-emit-workspace --format requirements.txt --output-file .tmp-audit-requirements.txt
uv run pip-audit --strict --ignore-vuln PYSEC-2026-113 --requirement .tmp-audit-requirements.txt
Remove-Item .tmp-audit-requirements.txt
pnpm audit --audit-level high
docker run --rm -v "${PWD}:/repo" ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f detect --source=/repo --config=/repo/.gitleaks.toml --no-banner --redact
```

`PYSEC-2026-113` is ignored because Apache documents the issue as Arrow C++ IPC
pre-buffering that Python bindings do not expose. Packet 8 keeps
`pyarrow==19.0.1`. See [ADR-cve-pin-patch-2026-08.md](../adr/ADR-cve-pin-patch-2026-08.md).

The Phase 10 Packet 1 gate reviews isolated staging IaC (encrypted IMDSv2
EC2, CloudFront 90s timeouts, digest-pinned ParadeDB/Valkey, Vercel public
keys only). It is local-only and is not a GitHub PR job. Zero collected
Packet 1 tests fail the gate. Live AWS/Supabase/Vercel/SES apply is Blocked
when Terraform/OpenTofu or the AWS session is missing. Do not run
`aws login` or `terraform apply` from this gate. See
[MANAGED_STAGING.md](../deployment/MANAGED_STAGING.md).

The Phase 10 Packet 2 gate reviews GitHub OIDC trust, named SSM documents,
protected workflows, secret-prefix custody, and the immutable migration
hash. It reuses `scripts/ci/check_migrations.py`. Live OIDC assume, SSM
migrate, and Secrets Manager rotation stay Blocked. It is local-only and is
not a GitHub PR job. Zero collected Packet 2 tests fail the gate. Do not
run `aws sts assume-role-with-web-identity` or `ssm send-command` from this
gate.

The Phase 10 Packet 3 gate reviews direct-origin denial, unpublished
private ports, provider/crawl/parser/ParadeDB egress, WAF/Caddy 90s
timeouts, and CloudWatch denial-filter IaC. It reuses
`tests/unit/test_crawl_policy.py` and `tests/contract/test_crawl_ssrf.py`
and fails if that subset collects zero tests or skips. Live CDN requests,
port scans, and alarm delivery stay Blocked. It is local-only and is not a
GitHub PR job. Do not curl CloudFront, nmap the origin, or invent HTTP
200/403 from this gate.

The Phase 10 Packet 4 gate reviews application JWKS (no HS256), origin
dual-header policy plus the origin-secret rotation runbook, 90s timeout
assertions, ParadeDB degrade/rebuild-not-canonical, and Valkey fail-closed
tests. Live managed JWKS dashboard rollover, live origin rotation, the
50-second CloudFront SSE timeline, and EC2 ParadeDB/Valkey kill stay
Blocked. Local EventSource is not CDN. It is local-only and is not a
GitHub PR job. Packets 1–3 remaining unchecked is not a Packet 4 failure.

The Phase 10 Packet 5 gate reviews KMS/S3 Object Lock IaC, SNS/budget
alarm routing, SES sandbox, 70% pause, local 30<42 connection math, and
the signed reduced envelope. Live PutObject, SNS ack, SES send, managed
Pro pooling, and EC2 measurements stay Blocked. HMAC is not KMS. It is
local-only and is not a GitHub PR job. Packets 1–4 remaining unchecked
is not a Packet 5 failure.

The Phase 10 Packet 6 gate reviews Storage/database reconciliation,
derived BM25 rebuild lineage, instance-rebuild targets, old-API/new-schema
smoke, and expand/contract. Live managed PITR, live reconciliation, timed
EC2 rebuild, and live Caddy/Vercel drain stay Blocked. Local dump is not
PITR. ParadeDB snapshots are not canonical. Rebuild before reconcile is
Failed. It is local-only and is not a GitHub PR job. Packets 1–5 remaining
unchecked is not a Packet 6 failure.

The Phase 10 Packet 7 gate consumes committed Packets 1–6 gate matrices
and records an honest no-go: the production-equivalent suite and
independent assessment remain Blocked, committed custody/IaC can Pass, and
promotion inputs stay pending. It does not re-run Packets 1–6 pytest, does
not invent a pentest report, and does not treat Trivy as Packet 7-C. It is
local-only and is not a GitHub PR job. Checking a Phase 10 checkbox or
setting the wrapper complete is Failed.

```powershell
uv run python scripts/phase10_staging.py assert-iac
uv run python scripts/ci/check_phase10_packet1.py
uv run python scripts/ci/check_phase10_packet2.py
uv run python scripts/ci/check_phase10_packet3.py
uv run python scripts/ci/check_phase10_packet4.py
uv run python scripts/ci/check_phase10_packet5.py
uv run python scripts/ci/check_phase10_packet6.py
uv run python scripts/ci/check_phase10_packet7.py
```

[docs index](../README.md) · [CI tiers](./CI_TIERS.md) · [Pyright baseline](./PYRIGHT_BASELINE.md) · [Managed staging](../deployment/MANAGED_STAGING.md)
