---
title: Stitch visual composition map
owner: engineering-lead
status: draft
last-reviewed: 2026-08-24
audience: frontend, reviewers
---

# Stitch visual composition map

Historical route-to-screenshot map for the Stitch export. On 2026-08-24
the user rejected those screenshots as the live composition target. They
remain local historical references only (gitignored
`docs/stitch_smart_rag_enterprise_console/`; not a CI docs target). Do
not import that folder. Current composition is the light Precision
Workspace in [STITCH_BRIEF.md](./STITCH_BRIEF.md) and
[DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md).

Related: [ADR-stitch-first-ux.md](../adr/ADR-stitch-first-ux.md) ·
[STITCH_REVIEW.md](./STITCH_REVIEW.md) ·
[STITCH_BRIEF.md](./STITCH_BRIEF.md) ·
[DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) ·
[docs index](../README.md)

```mermaid
flowchart LR
  signIn["frame_01"] --> login["/login"]
  chat["frame_04 chat"] --> home["/"]
  library["frame_06 plus 07"] --> docs["/documents"]
  detail["frame_09"] --> docId["/documents/id"]
  graphFrame["frame_10"] --> graph["/graph"]
  tablesFrame["frame_05"] --> tables["/tables"]
  usageFrame["frame_14"] --> usage["/usage"]
  primitives["frame_00"] --> shell["AppShell and admin routes"]
```

## Mapping

| Stitch frame | Product surface | Composition to preserve | Must omit |
| --- | --- | --- | --- |
| `frame_00_design_system` | Shared primitives | Buttons, badges, chips, inputs, tables, 8px radius, tonal elevation | Gallery route |
| `frame_01_sign_in` | `/login` and other Auth cards | Centered card, brand, form first, Google secondary | Console nav, fixtures, “all systems operational” mocks |
| `frame_03_owner_setup_invitations` | `/team` invite/offboard only | Invitation summary density | Owner-bootstrap wizard |
| `frame_04_main_chat_auto_routing` | `/` | Sidebar, top bar, transcript, sticky composer, pipeline, right diagnostics | Hybrid/Combined send, nDCG, TTFB, confidence mocks |
| `frame_04_chat_state_gallery` | States inside `/` | Verified/partial/refusal/reconnect patterns | Gallery route, glass blur |
| `frame_05_structured_table_result` | `/tables` | Deterministic table vs commentary split | SQL textarea, fake LLM panel |
| `frame_06_document_library` | `/documents` | Filters, table/cards, status badges, upload CTA | Invented scan/PII |
| `frame_07_file_upload_ingestion_flow` | Upload on `/documents` | Drop zone + attestation + progress | Extra ingest route |
| `frame_09_document_detail_audit` | `/documents/[documentId]` | Metadata, ingestion, graph, tables | Audit/PII/source-preview tabs |
| `frame_10_graph_explorer` | `/graph` | Three panes, search, bounded viz, evidence | Depth 5, Edit Relationship, unauthorized titles |
| `frame_14_usage_budgets_dashboard` | `/usage` | Meter dashboard hierarchy | Budget sliders, Slack, export-without-tool |

`/signup`, `/forgot-password`, `/auth/reset`, `/invitations/accept`
reuse the `frame_01` card. `/team`, `/tools`, `/curation`, `/profile` reuse
`frame_00` primitives and the authenticated shell.

## Local screenshot paths

Paths are relative to `docs/stitch_smart_rag_enterprise_console/` and are
gitignored. Open them on disk; do not add Markdown image links that CI
must resolve.

| Frame folder | File |
| --- | --- |
| `frame_01_sign_in/` | `screen.png` |
| `frame_04_main_chat_auto_routing/` | `screen.png` |
| `frame_06_document_library/` | `screen.png` |
| `frame_07_file_upload_ingestion_flow/` | `screen.png` |
| `frame_09_document_detail_audit/` | `screen.png` |
| `frame_10_graph_explorer/` | `screen.png` |
| `frame_05_structured_table_result/` | `screen.png` |
| `frame_14_usage_budgets_dashboard/` | `screen.png` |
| `frame_00_design_system/` | `screen.png` |

## Verification

Desktop **1280×800** and mobile **390×844**. Login form must be in the
first mobile viewport. Chat must prioritize transcript and composer.
Intentional deviations need a contract, accessibility, or responsive
reason in the evidence note.

Playwright captures live in
`apps/frontend/tests/e2e/visual-routes.spec.ts` (baselines under
`visual-routes.spec.ts-snapshots/`). Authenticated product-route
snapshots require local GoTrue and FastAPI.
