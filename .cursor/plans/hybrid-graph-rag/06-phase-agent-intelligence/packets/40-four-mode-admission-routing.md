---
phase: 6
packet: 40
status: complete
title: "Implement four-mode admission, Auto default, exactly-one-source routing, and Web envelope."
requirement_ids: [P06-40]
---

# Packet 40 — Implement four-mode admission, Auto default, exactly-one-source routing, and Web envelope.

Read and enforce [`../00-shared-contracts.md`](../00-shared-contracts.md).

Named skills:
[`implement-query-agent`](../../../../../.cursor/skills/implement-query-agent/SKILL.md),
[`implement-api-security`](../../../../../.cursor/skills/implement-api-security/SKILL.md).

Do not load frontend skills.

## Preconditions

- P06-37 is recorded. Inspect `RequestedSearchScope`,
  `apply_requested_search_scope`, `admit_query_run_v2` CHECK, envelopes,
  `Phase6RouteFamily`, `BranchKind`, `KnowledgeScope`, graph topology,
  and OpenAPI. Never edit an applied migration.

## Allowed outputs

- Next admission RPC/migration that adds `'web'` to the requested-scope
  CHECK without replacing v2
- `RequestedSearchScope.WEB`, `KnowledgeScope.WEB`,
  `Phase6RouteFamily.WEB_RESEARCH`, `BranchKind.WEB_RESEARCH`
- Auto/forced mapping, conflict-clarification, fail-closed `web_scope`
  stub when Web is disabled or unconfigured
- Envelope: forced Web reserves `WEB_RESEARCH` (50s, 5 model, 5 tools).
  Auto still reserves Composite. Web never Hybrid-clamps. If the Web
  envelope cannot fit inside Composite, reject
- `answer_origin="web"` on the wire
- Tests: `tests/unit/test_web_scope_routing.py`, additive admission
  contract, envelope, and OpenAPI tests
- Routing/admission docs and packet evidence

## Forbidden outputs

- Blended company+web retrieval or citation
- Company-insufficient fallback to Web or general
- Optional-tool catalog `web_search`
- Graph synthesis, Exa calls, or frontend dropdown
- Changing P06-10 company/general/mixed contracts except additive Web
- Silent Hybrid clamp of Web

## Ordered actions

1. Add `'web'` to the next admission contract. Keep v2 for old clients.
2. Default omitted request to Auto. Persist `requested_search_scope`.
3. Auto routing: company signals → company; explicit/current public
   web → `web`; ordinary world knowledge → general; company+web conflict
   → clarification; greetings/user-text keep existing paths.
4. Forced `web` returns `web_scope` even without company signals.
5. Disabled/unconfigured Web returns typed fail-closed
   (`web_search_disabled` / `web_search_unconfigured`).
6. Stub `web_scope` node until P06-41. Do not retrieve company evidence
   on that path.
7. Do not send company text, conversation memory, IDs, or secrets to
   any future Exa call.

## Acceptance checks

- Auto company/general/web/conflict/greeting cases settle as specified.
- Forced Web never searches company documents.
- Forced company never searches the web.
- Disabled Web is typed fail-closed, not a silent general answer.
- Envelope reservation matches the route family.
- OpenAPI includes `web` and `answer_origin="web"`.

## Negative tests

- Invalid requested scope remains 422.
- Company-insufficient evidence still never becomes Web.
- Optional-tool catalog still has no `web_search`.

## Stop routes

- Stop if Auto would retrieve company and web in one run.
- Stop if the CHECK cannot add `'web'` additively.
- Stop if envelope growth would exceed Composite.

## Required evidence

- Routing tables, admission CHECK, envelope numbers, fail-closed codes,
  and handoff to P06-41.
