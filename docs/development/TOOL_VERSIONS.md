---
title: Tool and dependency versions (Phase 1)
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
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
| Vitest | [Vitest guide](https://vitest.dev/guide/) |
| Playwright | [Playwright test documentation](https://playwright.dev/docs/intro) |
| Markdown lint | [markdownlint-cli2](https://github.com/DavidAnson/markdownlint-cli2) |
| Mermaid render | [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli) |

## Direct Python pins (members)

| Distribution | Pin |
| --- | --- |
| hatchling (build-system) | 1.32.0 |
| langgraph | 1.2.11 |
| langgraph-cli (dev) | 0.4.31 |
| fastapi | 0.141.1 |
| uvicorn[standard] | 0.52.1 |
| pydantic | 2.13.4 |
| pydantic-settings | 2.15.0 |
| typing-extensions | 4.16.0 |
| pytest (dev) | 9.1.1 |
| Ruff (dev) | 0.16.2 |
| Pyright (dev) | 1.1.411 |
| pre-commit (dev) | 4.6.2 |
| PyYAML (dev) | 6.0.3 |

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

Frontend application package name: `smart-rag-frontend`.

## Workspace members

| Ecosystem | Members |
| --- | --- |
| uv | `apps/agents`, `apps/backend`, `apps/worker`, `packages/core` |
| pnpm | `apps/frontend` |
