---
title: What this codebase already does unusually well
owner: independent-reviewer
status: draft
last-reviewed: 2026-08-19
audience: engineering, client-approver
reviewed_commit: 09a102a
---

# What is already excellent

A NO-GO review that only lists holes would mis-teach the team to rip out the good machinery. Keep these properties while you harden.

## Security discipline

- Asymmetric JWKS, HS256 in a forbid set, unknown-kid tests, local issuer aliases **only** when `APP_ENV=local`.
- Identity from live membership, not editable user_metadata.
- Isolated Auth Admin / Storage Admin settings classes, runtime `service_role` hunted by tests.
- Retrieval RPCs not granted to `service_role`.
- Hash-chained audit path (documented and tested in earlier phases).
- Deny-by-default external processing with an actual reason code.
- Parser/crawl/BM25 treated as untrusted until Supabase recheck.

## RAG discipline

- Canonical passages as the only prose evidence.
- Graph as leads with mapping/survival, not as a second wiki.
- Combined fusion bounded (agreement factor, graph-only cap) rather than naive union.
- Invented citation IDs dropped; spans must occur in canonical text (**empty spans still pass** — H-024; keep the stripper, tighten the check).
- Mock mode that **refuses query-ready** instead of silently "working."
- Live SSE still compiles an unbound graph (C-009) — do not confuse library excellence with a wired production path.

## Product discipline

- Limitation codes instead of hallucinated figure readings.
- Viewer chrome is convenience; FastAPI still 403s.
- SSE schema version handshake.
- Evidence files that say Not Run. That honesty is rarer than another dashboard.

## Engineering discipline

- uv/pnpm monorepo boundaries, distroless non-root API, digest-pinned images.
- Packet evidence with mermaid and gate matrices.
- QUALITY_TARGETS as numbers, then ADRs that **reduce** the envelope instead of moving the goalposts in silence.
- Google-style Python docstrings **present** on every authored definition (`test_docstrings.py`). Query nodes include State inputs/outputs and failure routes.
- C4 docs under `docs/architecture/` are actually split (context, containers, components, deployment).
- Settings fields have `description=`. Environment reads are confined to the settings package.

Do **not** confuse that with small files. `api.ts` is 1819 lines. Phase 6 evidence is 1259 lines. Keep the contracts; split the god files. See [code-quality](./domain/code-quality.md).

The gap is not "this RAG is a toy." The gap is "this RAG has not yet earned the word production." That is a better problem than the reverse.
