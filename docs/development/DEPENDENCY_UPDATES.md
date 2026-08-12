---
title: Dependency updates
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# Dependency updates

1. Change pins in member `pyproject.toml` / frontend `package.json`.
2. `uv lock` / `pnpm install` from repo root only.
3. Re-verify digests for third-party images in `infra/paradedb/IMAGE_DIGESTS.md`.
4. Run `uv run python scripts/check.py --tier fast`.
5. Record versions in [TOOL_VERSIONS.md](./TOOL_VERSIONS.md).

Never hand-edit lock package entries. Never regenerate lockfiles inside Docker images.

[docs index](../README.md)
