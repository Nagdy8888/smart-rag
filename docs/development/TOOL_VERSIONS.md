---
title: Tool and dependency versions (Phase 1)
owner: engineering-lead
status: draft
last-reviewed: 2026-08-15
audience: engineering
---

# Tool and dependency versions

Recorded during Phase 1 Packets 2–4 from host tools, current primary documentation, and package registries. Lockfiles are authoritative for transitive resolution.

## Host tooling (verified on authoring machine)

| Tool | Version | Notes |
| --- | --- | --- |
| uv | 0.11.23 | [uv documentation](https://docs.astral.sh/uv/) |
| Python (workspace) | 3.11.x (`requires-python = >=3.11,<3.13`) | Selected via uv |
| Node.js | 20.20.2 | Engine `>=20` |
| pnpm | 9.15.0 | `packageManager` in root `package.json` |

## Primary documentation used

| Concern | Source |
| --- | --- |
| uv workspaces / `package = false` | [uv workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/) |
| LangGraph `langgraph.json` | [LangGraph CLI configuration](https://docs.langchain.com/langsmith/cli#configuration-file) |
| Next.js App Router + TypeScript | [Next.js documentation](https://nextjs.org/docs) (create-next-app / TS config) |
| Pydantic Settings | [Pydantic Settings documentation](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| Ruff format/lint/pydocstyle | [Ruff documentation](https://docs.astral.sh/ruff/) |
| Pyright strict configuration | [Pyright configuration](https://github.com/microsoft/pyright/blob/main/docs/configuration.md) |
| Python dependency audit | [pip-audit](https://github.com/pypa/pip-audit) |
| Supabase local CLI | [Supabase CLI](https://supabase.com/docs/reference/cli/introduction) |
| Secret scan | [Gitleaks Action](https://github.com/gitleaks/gitleaks-action) |
| Vitest | [Vitest guide](https://vitest.dev/guide/) |
| Playwright | [Playwright test documentation](https://playwright.dev/docs/intro) |
| Markdown lint | [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2) |
| Mermaid render | [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) |

## Direct Python pins (members)

| Distribution | Pin |
| --- | --- |
| hatchling (build-system) | 1.32.0 |
| langgraph | 1.2.11 |
| langgraph-checkpoint-postgres | 3.1.2 |
| langgraph-cli (dev) | 0.4.31 |
| fastapi | 0.141.1 |
| uvicorn[standard] | 0.52.1 |
| pydantic | 2.13.4 |
| pydantic-settings | 2.15.0 |
| lightrag-hku (core / GraphRAG pin) | 1.5.6 |
| asyncpg (core / LightRAG pool) | 0.31.0 |
| pgvector (core / LightRAG vectors) | 0.5.0 |
| langsmith | 0.10.18 |
| openai (core) | 2.26.0 |
| typing-extensions | 4.16.0 |
| pytest (dev) | 9.1.1 |
| Ruff (dev) | 0.16.2 |
| Pyright (dev) | 1.1.411 |
| pre-commit (dev) | 4.6.2 |
| PyYAML (dev) | 6.0.3 |
| pip-audit (dev) | 2.10.1 |
| lxml (core / parser sandbox) | 6.1.0 |
| Pillow (core / parser sandbox) | 12.3.0 |
| pyarrow (core) | 19.0.1 |
| PyJWT[crypto] | 2.13.0 |

## Direct Node pins

| Package | Version |
| --- | --- |
| next | 16.3.0 |
| react / react-dom | 19.2.8 |
| typescript | 5.9.3 |
| eslint-config-next | 16.3.0 |
| Vitest | 4.1.10 |
| Playwright Test | 1.62.1 |
| markdownlint-cli2 (root) | 0.23.2 |
| Mermaid CLI (root) | 11.16.0 |
| Puppeteer (root) | 25.6.0 |
| Supabase CLI (root) | 2.114.0 |

## Security scan pins

| Scanner | Pin |
| --- | --- |
| Gitleaks Action | v3.0.0 commit `e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e` |
| Gitleaks CLI | 8.30.1 / image index `sha256:c00b6bd0aeb3071cbcb79009cb16a60dd9e0a7c60e2be9ab65d25e6bc8abbb7f` |

## GitHub Action runtime pins

| Action | Release / commit |
| --- | --- |
| `actions/checkout` | v7.0.1 / `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| `actions/setup-node` | v7.0.0 / `820762786026740c76f36085b0efc47a31fe5020` |
| `actions/setup-python` | v7.0.0 / `5fda3b95a4ea91299a34e894583c3862153e4b97` |
| `astral-sh/setup-uv` | v10.0.0 / `ae62891fec2bb8e7d6c99fc78c9fec3a63790f8d` |
| `pnpm/action-setup` | v6.0.10 / `ff378ebe6b225b0680b81c1ad4498ae0d1d3a5e3` |

Frontend application package name: `smart-rag-frontend`.

## Workspace members

| Ecosystem | Members |
| --- | --- |
| uv | `apps/agents`, `apps/backend`, `apps/worker`, `packages/core` |
| pnpm | `apps/frontend` |
