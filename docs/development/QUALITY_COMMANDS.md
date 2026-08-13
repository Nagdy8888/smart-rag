---
title: Quality commands
owner: engineering-lead
status: draft
last-reviewed: 2026-08-13
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
uv run python scripts/ci/check_phase2_integration.py
```

The schema determinism gate is intentionally destructive and local-only. With
the pinned Supabase stack running, it resets the local database exactly twice,
runs the authoritative schema contract after each reset, and compares roles,
extensions, tables, columns, constraints, private-schema exposure, and generated
types:

```powershell
uv run python scripts/ci/check_schema_determinism.py
```

The ordinary contract and fast tiers may skip live integration checks when their
local Supabase or ParadeDB prerequisites are unavailable, which keeps
dependency-only CI deterministic. The Phase 2 integration gate requires or
starts local Supabase and the private ParadeDB service, then runs the mandatory
schema/RLS/Auth/Storage/audit/BM25 suite. Any skipped mandatory test fails the
gate. Managed pgvector and JWKS rollover checks are deliberately reported as
separate, not silently skipped as local proof:

```powershell
uv run python scripts/ci/check_phase2_integration.py
```

Tiers hard-fail (no `|| true`). Zero collected tests fail the unit/contract tiers.
The frontend tier runs `next typegen` before standalone `tsc --noEmit`, so
route-aware `PageProps` and `LayoutProps` are available on a clean checkout.
Markdown checks cover maintained documentation. Preserved historical reviews in
`docs/prev_review/` and generated Stitch source exports in
`docs/stitch_smart_rag_enterprise_console/` are explicitly excluded and must
not be cited as current implementation evidence.

Dependency and secret scans use the locked Python/Node graphs and the same Gitleaks version as PR CI:

```powershell
uv export --frozen --all-packages --group dev --no-emit-workspace --format requirements.txt --output-file .tmp-audit-requirements.txt
uv run pip-audit --strict --requirement .tmp-audit-requirements.txt
Remove-Item .tmp-audit-requirements.txt
pnpm audit --audit-level high
docker run --rm -v "${PWD}:/repo" ghcr.io/gitleaks/gitleaks@sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f detect --source=/repo --no-banner --redact
```

[docs index](../README.md) · [CI tiers](./CI_TIERS.md)
