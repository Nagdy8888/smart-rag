---
title: CI tiers
owner: engineering-lead
status: draft
last-reviewed: 2026-08-13
audience: engineering
---

# CI tiers

| Tier | Workflow | Phase 1 behavior |
| --- | --- | --- |
| PR fast | `.github/workflows/pr-fast.yml` | full-history Gitleaks, locked installs, Python/Node dependency audits, plan integrity, `check.py --tier fast`, OpenAPI, and migration policy |
| Main | `.github/workflows/main.yml` | unit/contract tiers and Compose configuration validation |
| Nightly | `.github/workflows/nightly.yml` | full fast tier plus OpenAPI and migration policy |

**Future (not fake-green):** Supabase reset/RLS, LightRAG, retrieval evals, load, restore — Phases 2–10.

Actions are pinned by commit SHA. The workflows use `permissions: contents: read`; the secret scanner disables PR comments and artifact upload. A local workflow definition is not remote execution evidence, so a GitHub run URL and conclusion must be recorded separately.

[docs index](../README.md)
