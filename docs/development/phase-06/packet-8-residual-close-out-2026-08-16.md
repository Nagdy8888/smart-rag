# Packet 8 residual close-out (2026-08-16)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Closed the leftover local gaps that were still open after the first packet 8
handoff. Did **not** fake-pass later-phase gates.

## MFA upload (`signed_url=null`)

Password JWTs remain `aal1`. Tests now distinguish:

- `upload_enabled` + aal1 → `403 MFA required` (not a reservation)
- TOTP enroll/challenge/verify → aal2, then `signed_url` is JSON `null`

Local TOTP uses stdlib RFC 6238, not `pyotp`. `supabase/config.toml` enables
`[auth.mfa.totp]`. Restart Auth after that change if enroll is skipped:
`npx supabase stop && npx supabase start` (not `db reset`). The thin UI shows
an MFA-required banner for that 403.

This close-out run skipped the live Auth/Postgres tests because local
`:54322` was down and the Docker CLI did not respond. Re-run
`uv run python -m pytest tests/contract/test_thin_developer_ui_live.py`
after `npx supabase start`.

## Playwright Chromium

`scripts/check.py --tier frontend` installs Chromium (Linux CI:
`--with-deps`) and runs `playwright test`. It no longer stops at
`playwright --version`.

`pnpm --filter smart-rag-frontend exec playwright test tests/e2e/login.spec.ts`
exit 0: 2 passed (sign-in/outage copy, and readiness panel matched live
`GET /health/ready`).

## ParadeDB / LightRAG / Valkey through the browser

The console polls `GET /health/ready` (CORS allows `:3010`) and lists
`paradedb`, `valkey_limits`, `valkey_cache`, and `lightrag`. ParadeDB `down`
is an approved Hybrid degrade and is not BM25-snippet success. Signed
`bm25_unavailable` and `graph_outage` copy is always visible. Playwright
asserted the panel against the live readiness document. Compose stop of
ParadeDB/Valkey was not executed this run (Docker CLI hung). Packet 4/5 API
tests still own dense+term continuation and `graph_outage` emission. This is
not a mock `page.route` 503.

## Commands this close-out

| Command | Exit |
| --- | --- |
| `pnpm --filter smart-rag-frontend test` | 0 (26 passed) |
| `pnpm --filter smart-rag-frontend lint` | 0 |
| `pnpm --filter smart-rag-frontend typecheck` | 0 |
| `pnpm --filter smart-rag-frontend build` | 0 |
| `pnpm --filter smart-rag-frontend exec playwright install chromium` | 0 |
| `pnpm --filter smart-rag-frontend exec playwright test tests/e2e/login.spec.ts` | 0 (2 passed) |
| `uv run python -m pytest tests/unit/test_rfc6238_totp.py tests/unit/test_readiness.py` | 0 |
| `uv run python -m pytest tests/contract/test_thin_developer_ui_live.py` | 0 (6 skipped: local Postgres `:54322` down) |

## Still unverified (do not claim)

| Gate | Why it stays open |
| --- | --- |
| QT-EVAL-009 live Combined +10pp | Holdout sealed; registry must stay `unverified`; needs live mapping/extraction on the disjoint labeled set (Phase 9) |
| Live OpenAI answer/verifier | `MOCK_MODEL_MODE=true` local default; CI requires mock default |
| Hosted Auth throttling | `LOCAL_AUTH_THROTTLING_PROVEN = False`; packet 8 forbids managed cloud Auth for this E2E |
| Phase 10 CDN / CloudFront | Local proof is `signed_url=null`, not a signed CloudFront URL |

**Please accept Phase 6** if the local Done-when evidence is enough, or keep
the table above as explicit blockers.
