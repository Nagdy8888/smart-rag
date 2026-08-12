---
title: Local admin alert contract
owner: engineering-lead
status: draft
last-reviewed: 2026-08-12
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

Implementation of the alert UI/API is Phase 6/8. This document is the normative field contract.

[docs index](../README.md)
