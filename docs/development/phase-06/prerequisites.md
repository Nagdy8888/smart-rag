# Prerequisites

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

| Prerequisite | Evidence |
| --- | --- |
| Phases 1–5 accepted | [phase-05-graphrag-evidence.md](../phase-05-graphrag-evidence.md) status `accepted` |
| JWT/profile `CallerContext` | `smart_rag_core.security.identity` plus FastAPI JWKS loader |
| Durable budgets | `app.budget_reservations` kinds were `ingestion_daily` / `graph_index` / `graph_maintenance` |
| Audit chain | `app.append_audit_event` / `app.authorize_restricted_read` |
| `Phase6RouteFamily` | `smart_rag_core.query_profile.phase6_map` |
