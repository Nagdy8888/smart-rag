---
title: Local release candidate (retired)
owner: engineering-lead
status: retired
last-reviewed: 2026-09-07
audience: engineering, ops
---

# Local release candidate (retired)

The Phase-9 local release-candidate runbook was removed with the local
Supabase CLI fixture. Runtime, E2E, and operator scripts target the cloud
project only. Destructive schema suites stay opt-in via an explicit
non-hosted `SUPABASE_DB_URL`.
