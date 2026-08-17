---
title: Quality commands
owner: engineering-lead
status: draft
last-reviewed: 2026-08-17
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
uv run python scripts/phase09_candidate.py all
uv run python scripts/ci/check_phase09_packet1.py
uv run python scripts/ci/check_phase09_packet2.py --mode candidate
```

GitHub CI invokes one `--tier` per job (or a paired reusable job such as
`format-lint` / `docs-frontend`). It does not run `--tier fast` as a single
GitHub job. Local `uv run python scripts/check.py --tier fast` still exists
and still includes `types`. Parallel job membership:
[CI_TIERS.md](./CI_TIERS.md).

When `CI=true`, `check.py` appends `--tb=short -ra` to the unit and
contract pytest invocations. Local runs without that environment variable
keep pytest’s default traceback style.

The schema determinism gate is intentionally destructive and local-only. With
the pinned Supabase stack running, it resets the local database exactly twice,
runs the authoritative schema contract after each reset, and compares roles,
extensions, tables, columns, constraints, private-schema exposure, and generated
types. Type generation uses `--db-url` against host `127.0.0.1:54322`. The gate
wipes any Phase 9 seed; reseed immediately on candidate compose only.

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

The Phase 9 Packet 1 candidate gate freezes digest-bound images, unpublished
private ports, and the approved open-split corpus. It is local-only and is
not a GitHub PR job. Zero collected Packet 1 tests fail the gate. Live
Compose/Supabase artifact checks skip unless
`SMART_RAG_REQUIRE_PHASE09_CANDIDATE=1`. See
[LOCAL_RELEASE_CANDIDATE.md](../deployment/LOCAL_RELEASE_CANDIDATE.md).

Do not retry Packet 1 Trivy via `docker run aquasec/trivy` mounting
`docker.sock` on this Windows host until Packet 6: the 2026-08-17 attempt
hung Docker Desktop (HTTP 500), left WSL `vmmemWSL` StopPending, and filled
the disk with a Docker Desktop updater download. Compact scan status is
Blocked in `docs/deployment/phase-09/candidate-scan-summary.json`.

```powershell
uv run python scripts/phase09_candidate.py all
uv run python scripts/ci/check_phase09_packet1.py
```

The Phase 9 Packet 2 gate is also local-only and is not a GitHub PR job. It
fail-closes on zero collection, failures, errors, or skipped mandatory local
tests. `--mode candidate` uses unpublished ParadeDB via `docker compose exec`.
`--mode overlay` requires `docker-compose.packet8.yml` already attached for
ClamAV, crawl-proxy, and host-side BM25 tests; detach the overlay afterward
and re-prove unpublished ports. Overlay merge must use `--merge-artifact` so
candidate suite rows are not clobbered. Do not set
`SMART_RAG_HOLDOUT_ACCESS=true`. `check_schema_determinism.py` wipes Packet 1
seed; reseed immediately with `phase09_candidate.py seed` on candidate compose
only (worker `exec` copies artifacts; `compose cp` cannot see worker `/tmp`
tmpfs). Old-API/new-schema authenticated smoke has no existing repository
script; Packet 2 records it Blocked rather than inventing a pass. Managed
JWKS/CDN/KMS/OIDC/restore/assessment stay Phase 10 handoffs. Do not retry
Trivy via docker.sock.

```powershell
uv run python scripts/ci/check_phase09_packet2.py --mode candidate
uv run python scripts/ci/check_phase2_integration.py
uv run python scripts/ci/check_openapi.py
uv run python scripts/ci/check_migrations.py
uv run python scripts/ci/check_schema_determinism.py
uv run python scripts/phase09_candidate.py seed
uv run python scripts/phase09_candidate.py sizing
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --no-build --wait clamav paradedb crawl-proxy
$env:SMART_RAG_REQUIRE_CLAMAV = "1"
$env:SMART_RAG_REQUIRE_CRAWL_PROXY = "1"
uv run python scripts/ci/check_phase09_packet2.py --mode overlay --merge-artifact
Remove-Item Env:SMART_RAG_REQUIRE_CLAMAV
Remove-Item Env:SMART_RAG_REQUIRE_CRAWL_PROXY
docker compose --env-file .env.compose -f docker-compose.yml up -d --no-build --wait --remove-orphans
uv run python scripts/phase09_candidate.py ports-static
uv run python scripts/phase09_candidate.py health
```

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

[docs index](../README.md) · [CI tiers](./CI_TIERS.md) · [Pyright baseline](./PYRIGHT_BASELINE.md) · [Local release candidate](../deployment/LOCAL_RELEASE_CANDIDATE.md)
