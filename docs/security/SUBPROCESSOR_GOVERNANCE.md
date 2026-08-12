---
title: Subprocessor governance
owner: product-owner
status: draft
last-reviewed: 2026-08-12
audience: client-approver, security
---

# Subprocessor governance (draft)

**Status: draft — not signed.**

| Subprocessor | Purpose | Data classes | Status |
| --- | --- | --- | --- |
| OpenAI | chat, embeddings, rerank, extraction | bounded evidence/prompts | draft |
| Supabase | Auth, DB, Storage | application + files | draft |
| LangSmith | traces/evals | redacted traces | draft |
| Vercel | frontend hosting | public config / browser | planned |
| AWS (staging+) | EC2, SES, CloudFront | runtime / email | planned |

Together with [OPENAI_DATA_GOVERNANCE.md](./OPENAI_DATA_GOVERNANCE.md) this forms one external-processing governance packet.

[docs index](../README.md)
