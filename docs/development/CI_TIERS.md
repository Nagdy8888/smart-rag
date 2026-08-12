---
title: CI tiers
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# CI tiers

| Tier | Workflow | Phase 1 behavior |
| --- | --- | --- |
| PR fast | `.github/workflows/pr-fast.yml` | plan integrity (when present), locked installs, `check.py --tier fast`, OpenAPI + migration static checks |
| Main | `.github/workflows/main.yml` | Compose config validate, unit/contract, image build matrix when Docker available |
| Nightly | `.github/workflows/nightly.yml` | dependency audit notes + full fast tier |

**Future (not fake-green):** Supabase reset/RLS, LightRAG, retrieval evals, load, restore — Phases 2–10.

Actions pinned by commit SHA. `permissions: contents: read` default.

[docs index](../README.md)
