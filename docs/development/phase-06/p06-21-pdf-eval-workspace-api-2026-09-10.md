# P06-21 — PDF eval workspace API (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Local-only owner/admin HTTP overlay. Disabled by default. Staging and
production reject `PDF_EVAL_WORKSPACE_ENABLED=true` at settings load. Routes
register only when enabled and `APP_ENV` is `local` or `test`.

Requirement: status, cases, PATCH, approve/reject, drafts, passages, latest
report, compare-run. Reviewer is `caller.user_id`. Passages use `app_api`.

Files:

- [`apps/backend/src/smart_rag_api/routers/pdf_eval.py`](../../../apps/backend/src/smart_rag_api/routers/pdf_eval.py)
- [`apps/backend/src/smart_rag_api/services/pdf_eval_workspace.py`](../../../apps/backend/src/smart_rag_api/services/pdf_eval_workspace.py)
- [`apps/backend/src/smart_rag_api/schemas/pdf_eval.py`](../../../apps/backend/src/smart_rag_api/schemas/pdf_eval.py)
- Additive settings, `/api/meta`, `create_app` registration, Compose bind mount
- [`supabase/migrations/20260910140000_list_authorized_eval_passages_v1.sql`](../../../supabase/migrations/20260910140000_list_authorized_eval_passages_v1.sql)
- [`tests/contract/test_pdf_eval_api.py`](../../../tests/contract/test_pdf_eval_api.py)
- [`docs/evaluation/PDF_EVAL_WORKSPACE.md`](../../evaluation/PDF_EVAL_WORKSPACE.md)
- [`docs/security/AUTHORIZATION_MODEL.md`](../../security/AUTHORIZATION_MODEL.md)
- [`docs/development/CONFIGURATION.md`](../CONFIGURATION.md)

Verification:

| Command | Exit |
| --- | --- |
| `uv run python -m pytest tests/contract/test_pdf_eval_api.py tests/unit/test_settings.py -k pdf_eval -q` | 0 (API file in overlay 139; settings 1 passed) |
| `uv run python scripts/check.py --tier types` | 0 |

Proven: member 403, disabled 404 with no OpenAPI `/admin/pdf-eval/status`,
stale revision 409, `split=holdout` 400, hosted env enablement fails closed,
list OpenAPI omits bulk question fields.

Unverified: live passage RPC against a mounted private PDF version.

Rollback: keep `PDF_EVAL_WORKSPACE_ENABLED=false`, drop route registration and
the Compose bind mount.

Handoff: Packet 22 owns the Admin Evaluation UI.
