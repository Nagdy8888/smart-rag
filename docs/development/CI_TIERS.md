---
title: CI tiers
owner: engineering-lead
status: draft
last-reviewed: 2026-08-16
audience: engineering
---

# CI tiers

| Tier | Workflow | Phase 1 behavior |
| --- | --- | --- |
| PR fast | `.github/workflows/pr-fast.yml` | full-history Gitleaks, locked installs, Python/Node dependency audits, plan integrity, `check.py --tier fast`, OpenAPI, and migration policy |
| Main | `.github/workflows/main.yml` | unit/contract tiers and Compose configuration validation |
| Nightly | `.github/workflows/nightly.yml` | full fast tier plus OpenAPI and migration policy |

The fast tier still includes `types`. That command is a real
`python -m pyright` run plus the error-count ratchet in
[QUALITY_COMMANDS.md](./QUALITY_COMMANDS.md). As of 2026-08-16 the local
full-repo count is **882** errors, so `types` is expected to fail until the
debt is paid. See [PYRIGHT_BASELINE.md](./PYRIGHT_BASELINE.md). A workflow
file is not remote execution evidence.

**Future (not fake-green):** Supabase reset/RLS, LightRAG, retrieval evals, load, restore — Phases 2–10.

Actions are pinned by commit SHA. The workflows use `permissions: contents: read`; the secret scanner disables PR comments and artifact upload. A local workflow definition is not remote execution evidence, so a GitHub run URL and conclusion must be recorded separately.

GitHub-hosted Ubuntu runners block the Chromium sandbox required by Mermaid
CLI. After the locked Node install, PR and nightly jobs use the pinned Puppeteer
CLI to install its compatible `chrome-headless-shell`, then pass the official
`--puppeteerConfigFile` workaround in `scripts/ci/puppeteer-no-sandbox.json`.
The explicit browser installation avoids depending on package lifecycle-script
behavior on a clean runner. The no-sandbox exception is limited to
least-privilege ephemeral CI jobs; local documentation checks retain the browser
sandbox.

[docs index](../README.md) · [Quality commands](./QUALITY_COMMANDS.md) · [Pyright baseline](./PYRIGHT_BASELINE.md)
