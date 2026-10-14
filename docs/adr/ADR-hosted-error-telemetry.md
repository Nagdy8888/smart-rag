---
title: ADR — Hosted GlitchTip and Grafana error telemetry
adr_id: ADR-hosted-error-telemetry
status: accepted
owner: engineering-lead
last-reviewed: 2026-10-13
approver: "user (Cursor chat; no legal name provided)"
approval_date: "2026-10-13"
audience: engineering, security, operators
---

# ADR: Hosted GlitchTip and Grafana error telemetry

## Status

`accepted` — 2026-10-13. The user asked for professional production error
logs using free tools, and chose Grafana Cloud plus GlitchTip rather than
a self-hosted stack on the 1 GB staging host.

## Context

Stdout JSON logs redact exception text and are kept only by whatever
collects the process output. `app.run_events` stores a short error code.
Job rows store `last_error`. None of those is an error-group view with
stack frames, or a searchable log store with a dashboard.

The staging host cannot run Grafana, Loki, or GlitchTip beside ParadeDB.

## Decision

1. Export is off unless `GLITCHTIP_ENABLED` or `OTEL_EXPORT_ENABLED` is
   true. A DSN, OTLP endpoint, or ingest header without its flag fails
   settings load. Enabling a flag without its credential also fails.
2. GlitchTip (Sentry SDK pointed at the free GlitchTip cloud) receives
   exception type, a message passed through `redact_text`, and stack
   frames limited to file, function, and line. Local variables, source
   context, cookies, auth headers, request bodies, and passage-like keys
   are removed. `send_default_pii` stays false.
3. Grafana Cloud OTLP receives the same fields as the stdout JSON line:
   level, service, environment, event, redacted message, correlation ids,
   `error_type`, and `exception_type`. Exception text stays redacted.
   Spans are `http.request`, `worker.job`, and `worker.bm25_job` with
   correlation ids only.
4. No collector container is added on the 1 GB host. The API, worker, and
   agent process export directly. The browser sends to GlitchTip only when
   `NEXT_PUBLIC_GLITCHTIP_DSN` is set, and the CSP `connect-src` allows
   that DSN origin.
5. `app.glitchtip.com` is on the provider-egress allowlist. The Grafana
   gateway hostname is account-specific and is added only after signup.

## Alternatives rejected

- Self-hosted Grafana and GlitchTip on the current server. The host is
  already at 1 GB.
- Grafana Cloud alone. Log lines would still hide the stack that GlitchTip
  keeps in scrubbed form.
- Sending raw exception messages. That would undo the existing secret and
  passage redaction.

## Consequences

Operators create the two free accounts and set the env vars before
production errors appear in either UI. Stdout logs, `app.run_events`, job
`last_error`, and `app.audit_events` stay unchanged.

[ERROR_TELEMETRY.md](../development/ERROR_TELEMETRY.md) ·
[CONFIGURATION.md](../development/CONFIGURATION.md) ·
[ADR index](./README.md)
