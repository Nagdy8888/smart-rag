---
title: Local admin alert contract
owner: engineering-lead
status: draft
last-reviewed: 2026-08-14
audience: engineering, operations
---

# Local admin alert contract

Phase 1 defines the **contract** for in-app/local admin alerts. Delivery channels and production routing are later phases.

| Field | Requirement |
| --- | --- |
| Severity | `info` / `warning` / `critical` |
| Audience | owner/admin roles only |
| Durability | alerts that affect security/budget must be durable in Supabase (not Valkey-only) |
| Ack | critical alerts require acknowledged-by + timestamp |
| Examples | budget exhausted, graph quarantine, Valkey degraded path, migration failure |

Phase 3 Packet 8: after `app.emit_admin_notification` persists a row, the worker/API best-effort sends a metadata-only SMTP copy to local Inbucket (`127.0.0.1:54325`, `ADMIN_ALERT_SMTP_*`). SMTP failure is logged and never deletes or rolls back the durable row.

Implementation of the alert UI/API is Phase 6/8. This document is the normative field contract.

[docs index](../README.md)
