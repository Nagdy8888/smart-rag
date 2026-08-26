---
title: ADR — Local-only LangSmith I/O export
adr_id: ADR-local-langsmith-export-io
status: accepted
owner: engineering-lead
last-reviewed: 2026-08-26
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-08-25"
audience: engineering, security
---

# ADR: Local-only LangSmith I/O export

## Status

`accepted` — 2026-08-25. The user asked to see prompt and completion text
in LangSmith on the laptop runtime.

## Context

Startup forced `LANGSMITH_HIDE_INPUTS` and `LANGSMITH_HIDE_OUTPUTS` so
`wrap_openai` child spans and application `process_inputs` / `process_outputs`
hooks export hashes, counts, and usage only. That is the production contract.
The laptop operator still needs to inspect live model I/O while debugging Ask.

## Decision (accepted)

1. Add `LANGSMITH_EXPORT_IO` (default `false`) on `SharedSettings`.
2. Honor it only when `APP_ENV=local` and tracing is on. Staging and
   production fail closed if the flag is true.
3. When honored, clear the hide-input/output SDK flags and attach prompt /
   completion text on gateway spans plus the user message and assistant
   reply on the `query.run.sse` parent (`input` / `output.text`). Token
   counts and estimated USD attach on that parent (LangSmith
   `usage_metadata` plus the Output object) and on gateway spans even when
   this flag is false. API keys, JWTs, and embedding vectors stay omitted.
4. Do not treat this flag as org-matrix verification. Real company files
   remain out of hosted environments on the local unsigned waiver.

## Alternatives rejected

| Option | Why not |
| --- | --- |
| Always export I/O | Violates the hide-I/O subprocessor contract |
| Honor the flag in staging | Sends private payloads to LangSmith without a verified matrix |
| Operator flips hide env vars by hand | Startup overwrites them; the typed flag is the only switch |

## Consequences

- A new Ask run after API restart is required before LangSmith shows bodies.
- Set `LANGSMITH_EXPORT_IO=false` (or unset it) to return to hashes/usage only.
