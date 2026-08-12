---
title: Local setup
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# Local setup

1. Install Docker Desktop (WSL2), uv, Node 20+, pnpm 9.15+, optional Supabase CLI.
2. `Copy-Item .env.example .env` and set passwords (KEY=VALUE only).
3. `uv sync --all-packages --group dev --python 3.11`
4. `pnpm install`
5. `.\scripts\dev.ps1`

See [CONFIGURATION.md](./CONFIGURATION.md), [TOOL_VERSIONS.md](./TOOL_VERSIONS.md), [docs index](../README.md).
