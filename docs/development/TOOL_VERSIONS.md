---
title: Tool and dependency versions (Phase 1 Packet 2)
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
audience: engineering
---

# Tool and dependency versions

Recorded during Phase 1 Packet 2 from host tools and primary registries. Lockfiles are authoritative for transitive resolution.

## Host tooling (verified on authoring machine)

| Tool | Version | Notes |
| --- | --- | --- |
| uv | 0.11.23 | https://docs.astral.sh/uv/ |
| Python (workspace) | 3.11.x (`requires-python = >=3.11,<3.13`) | Selected via uv |
| Node.js | 20.20.2 | Engine `>=20` |
| pnpm | 9.15.0 | `packageManager` in root `package.json` |

## Primary documentation used

| Concern | Source |
| --- | --- |
| uv workspaces / `package = false` | https://docs.astral.sh/uv/concepts/projects/workspaces/ |
| LangGraph `langgraph.json` | https://docs.langchain.com/langsmith/cli#configuration-file |
| Next.js App Router + TypeScript | https://nextjs.org/docs (create-next-app / TS config) |

## Direct Python pins (members)

| Distribution | Pin |
| --- | --- |
| hatchling (build-system) | 1.32.0 |
| langgraph | 1.2.11 |
| langgraph-cli (dev) | 0.4.31 |
| fastapi | 0.141.1 |
| uvicorn[standard] | 0.52.1 |
| pydantic | 2.13.4 |
| typing-extensions | 4.16.0 |
| pytest (dev) | 9.1.1 |

## Direct Node pins

| Package | Version |
| --- | --- |
| next | 16.3.0 |
| react / react-dom | 19.2.8 |
| typescript | 5.9.3 |
| eslint-config-next | 16.3.0 |

Frontend application package name: `smart-rag-frontend`.

## Workspace members

| Ecosystem | Members |
| --- | --- |
| uv | `apps/agents`, `apps/backend`, `apps/worker`, `packages/core` |
| pnpm | `apps/frontend` |
