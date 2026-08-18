---
title: Dependency updates
owner: engineering-lead
status: draft
last-reviewed: 2026-08-18
audience: engineering
---

# Dependency updates

1. Change pins in member `pyproject.toml` / frontend `package.json`.
2. `uv lock` / `pnpm install` from repo root only.
3. Re-verify digests for third-party images in `infra/paradedb/IMAGE_DIGESTS.md`.
4. Run `uv run python scripts/check.py --tier fast`.
5. Record versions in [TOOL_VERSIONS.md](./TOOL_VERSIONS.md).

Never hand-edit lock package entries. Never regenerate lockfiles inside Docker images.

Python `pip-audit --strict` currently ignores only `PYSEC-2026-113` (Arrow C++
IPC pre-buffering not exposed in `pyarrow` Python bindings). See
[ADR-cve-pin-patch-2026-08.md](../adr/ADR-cve-pin-patch-2026-08.md).

[docs index](../README.md)
