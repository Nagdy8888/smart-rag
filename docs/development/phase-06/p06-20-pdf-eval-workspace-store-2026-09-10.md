# P06-20 — PDF eval workspace store (2026-09-10)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Local private-file store and source-bound draft generation. HTTP callers never
supply a filesystem path. Holdout paths are rejected. Generated rows stay
`generated_only=true` and are never self-approved.

Requirement: bounded gitignored workspace at a server-owned root, SHA-256
compare-and-swap, approval reset on edit, extractive drafts.

Files:

- [`packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_store.py`](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_store.py)
- [`packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_models.py`](../../../packages/core/src/smart_rag_core/evaluation/private_pdf/workspace_models.py)
- Additive `draft.py`, `schema.py`, `__init__.py`
- [`tests/unit/test_pdf_eval_workspace_store.py`](../../../tests/unit/test_pdf_eval_workspace_store.py)
- Additive [`tests/unit/test_private_pdf_eval.py`](../../../tests/unit/test_private_pdf_eval.py)
- [`docs/evaluation/PDF_EVAL_WORKSPACE.md`](../../evaluation/PDF_EVAL_WORKSPACE.md)

Verification:

| Command | Exit |
| --- | --- |
| `uv run python scripts/check.py --tier format` | 0 |
| `uv run python scripts/check.py --tier lint` | 0 |
| `uv run python scripts/check.py --tier types` | 0 |
| `uv run python -m pytest tests/unit/test_pdf_eval_workspace_store.py tests/unit/test_private_pdf_eval.py -q` | 0 (included in overlay 139 passed) |

Proven: traversal/`holdout` rejection, stale revision conflict, atomic replace,
approval reset, no self-approve, exact-hash duplicate skip, log redaction of
questions/answers/roots.

Unverified: live operator reseal of drafts.

Rollback: delete the store modules and restore prior `draft.py` uniqueness
behavior.

Handoff: Packet 21 owns FastAPI routes, `/api/meta`, Compose mount, and
passage RPC.
