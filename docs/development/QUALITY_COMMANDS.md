---
title: Quality commands
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
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
```

Tiers hard-fail (no `|| true`). Zero collected tests fail the unit/contract tiers.

[docs index](../README.md) · [CI tiers](./CI_TIERS.md)
