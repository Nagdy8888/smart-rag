# Skill selection for Smart RAG

Reviewed and installed on 2026-10-23. Newer publication alone does not establish
better guidance. Selection is based on coverage of this repository's actual work.
All imported skills are project-local; existing skills were preserved.

## Primary project skills

Keep `implement-query-agent`, `implement-hybrid-retrieval`,
`implement-ingestion-pipeline`, `implement-lightrag-graph`,
`implement-structured-table`, `implement-api-security`,
`implement-supabase-security`, `implement-observability-evals`,
`implement-rag-frontend`, `scaffold-monorepo-layout`, `implement-plan-phase`,
and `verify-release-gates` for their existing domains. They encode the actual
Supabase authorization, canonical evidence, bounded calls, native assets,
phase contracts, and release requirements that general-purpose skills lack.

## Imported guidance to select by task

- `security-audit`: source-first security investigation and independent finding
  verification; supplements the implementation skills. Use guidance mode for
  focused reviews. A full audit has its own sandbox, coverage, and artifact
  requirements; installing it is not evidence of a completed security audit.
- `react-best-practices` (skill name `vercel-react-best-practices`): React/Next.js
  rendering, bundle, and data-fetch performance. Prefer its specific rules for
  measured frontend bottlenecks, while retaining authenticated streaming contracts.
- `web-design-guidelines`: current accessibility and interaction checks. Fetch its
  linked guideline source when reviewing; project copy conventions still apply.
- `impeccable`: retain the existing design workflow and established visual system.
  `ui-taste`, `frontend-design`, and `ui-ux-pro-max` add task-specific critique,
  design judgment, and searchable UX guidance. Select one lead workflow instead of
  stacking conflicting redesign procedures. A local fix preserves the app's design.
- `codebase-design`: interface depth, locality, and tests at existing interfaces.
  `improve-codebase-architecture` supports a dedicated architecture exploration;
  proposals must respect existing ADRs and need evidence before large refactors.
- `code-review`: use its separate standards/spec reviews when the comparison ref
  and specification are available. A review of an uncommitted worktree must include
  staged, unstaged, and new files; an empty commit diff proves nothing.
- `implement`: use with the project implementation skill and existing tests.
  Existing user conditions on committing and merging remain binding.
- `to-spec`: specification synthesis when needed. Existing approved plans are not
  rewritten merely because a new skill is installed. No issue is published as an
  installation side effect.
- `find-skills`: future skill discovery. Keep installations project-local unless
  the user asks for global scope; verify content before using it.
- `skill-creator`: authoring and evaluating new skills when requested. Its
  Claude-specific evaluation tools are not automatically required for this app.
- `setup-pre-commit`: retain the existing `.pre-commit-config.yaml` checks for Ruff,
  Pyright, unit, and contract tests. Do not add a competing Husky/Prettier pipeline
  or reformat immutable prompts and upstream files as a side effect.
- `git-guardrails-claude-code`: installed reference for Claude Code, not a Codex
  hook. Its default blocks every push, conflicting with the user's authorized
  push/merge workflow, so it is not activated. Preserve existing hook settings.
- `resolving-merge-conflicts`: archived upstream skill, recovered from the parent
  of removal commit `daa01d8aa68ad5c61b68970ec2018d0ce9567be6`. Use only for an
  actual conflict. User instructions take precedence over its categorical rules.
- `scaffold-exercises`: installed for future educational content; this app is not
  an AI Hero course, so do not create exercise directories or add its course CLI.
- `ios-design`: supplied by Uizze alongside `ui-taste`; available for a future
  native client. The current Next.js app does not become an iOS project.

## Installation and provenance

GitHub sources and exact commits are recorded in
[`skills/upstream-manifest.json`](skills/upstream-manifest.json), with per-file
SHA-256 hashes and retained license files. Uizze's well-known source additionally
has CLI-managed digests in [`../skills-lock.json`](../skills-lock.json).
`resolving-merge-conflicts` is explicitly archived; all other GitHub copies use the
current source commit observed at installation. No global model setting or
application dependency was changed to install the skills.

The latest Skills CLI requires Node 22.20 or newer. Uizze was installed with an
isolated `npx --package=node@22.22.0 --package=skills@1.7.4` invocation; the project's
Node installation and package lock were preserved. The two Uizze skills require
no paid MCP connection for local guidance. No account or paid connection was added.

New skills are available to discovery on the next turn; this session can already
read and apply the local files directly.

## Applied in this installation pass

- Read the existing project skill contracts and the imported entry points before
  choosing primary and supplemental workflows. No existing skill was overwritten.
- Applied UI/UX Pro Max's contextual status guidance, Vercel's live-region and
  code-translation rules, and Uizze's narrow-refinement workflow to the code-copy
  control. It now announces success/failure and preserves literal code from
  browser translation. The seven targeted checks and all 738 frontend tests pass;
  frontend TypeScript and focused ESLint pass. This was not a fresh visual audit.
- Retained the existing Ruff/Pyright/unit/contract pre-commit configuration and
  activated it with `uv run pre-commit install`; no competing hook stack was added.
- Applied codebase-design's preference for an existing interface: the accessibility
  correction stays inside the existing code-block module, tested through user actions.
- Used security-audit's source-first guidance for the changed code rendering and
  explicit user-note preservation. No full independent security audit is claimed.
- Verified all 243 installed skill files against the recorded hashes, including
  Uizze's supplied checksum manifests. Upstream utilities are retained verbatim;
  only their three Python tool directories are excluded from app-style Ruff and
  authored-code checks. A contract test keeps custom skills and identically named
  application directories covered.

The agent's 50-turn all-Luna live evaluation remains incomplete because the local
monthly budget admission guard rejected the next run. Installing skills does not
clear that gate, authorize a budget increase, or establish release readiness.
