# OpenTelemetry tracestate security patch

Date: 2026-10-23. Status: implemented during CI repair.

## Context

PR #21's dependency audit reported `CVE-2026-114603` against the previously pinned
`opentelemetry-api==1.37.0`. The upstream
[advisory](https://github.com/advisories/GHSA-xcq7-p3pf-p88h) identifies unbounded
tracestate parsing; the [1.45.1 release](https://github.com/open-telemetry/opentelemetry-python/releases/tag/v1.45.1)
contains the fix. No vulnerability suppression was added.

## Change

Pin the OpenTelemetry API, SDK, and OTLP HTTP exporter together to `1.45.1` and
regenerate the workspace lock. This keeps the exporter on its supported paired SDK
and retains the default requests transport.

The development-only `langgraph-cli[inmem]` dependency resolves `langgraph-api`
from `0.12.6` to `0.10.3` and `langgraph-runtime-inmem` from `0.32.6` to `0.30.3`.
The newer locked API required a legacy Prometheus exporter whose SDK constraint
conflicted with the patched SDK. The resolver selected the compatible development
server instead of overriding upstream requirements. This is an explicit dev-tool
tradeoff; the application's LangGraph orchestration and checkpoint libraries were
not downgraded. Revisit the development server when upstream's exporter constraint
supports this patched telemetry stack.

## Verification

The frozen, fully resolved requirements were audited locally with `pip-audit`
without reinstalling packages: no known vulnerabilities, with the same two
existing advisory aliases ignored by the repository's PyArrow exception. No new
ignore was added. The normal CI dependency audit remains unchanged.

A regression test exercises the actual W3C header propagation interface: normal
tracestate survives, oversized padded tracestate is discarded, and the valid parent
trace remains valid. The targeted telemetry/tracing suite passes 45 tests.
`langgraph dev --help` remains available. Full commit hooks and remote CI must
pass before merge; a CLI help check does not prove every development-server flow.
