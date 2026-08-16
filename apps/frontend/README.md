# Smart RAG frontend

Thin authenticated developer console for local Hybrid/Graph RAG testing.
This package is **not** the Stitch or production UI.

## Prerequisites

- `NEXT_PUBLIC_API_BASE_URL` (default `http://127.0.0.1:8000`)
- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`

See [THIN_DEVELOPER_UI.md](../../docs/frontend/THIN_DEVELOPER_UI.md).

## Commands

```bash
pnpm --filter smart-rag-frontend test
pnpm --filter smart-rag-frontend lint
pnpm --filter smart-rag-frontend exec tsc --noEmit
pnpm --filter smart-rag-frontend build
pnpm --filter smart-rag-frontend dev
```
