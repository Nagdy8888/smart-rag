# CI repair follow-up

Date: 21 October 2026. This follow-up addresses the failing GitHub checks on
`a2164952a3ea4bfd87879b2d6d6d0dadf5643f27` before publishing the agent repairs.

## Changes

- Use narrow typed interfaces at PyMuPDF boundaries and typed HTTP fixtures;
  full Pyright now reports zero errors without increasing its baseline.
- Give figure descriptions a metadata-only LangSmith span. The SDK payload
  wrapper stays disabled for this call, including when trace IO is enabled.
  Canary tests cover image, credential, URL, and description redaction.
  This does not resolve the separate figure-processing governance, durable
  accounting, or parser-isolation findings in the original security review.
- Scope citation page state to the selected citation and authentication session.
  Async completion updates state; cancellation discards stale results and releases
  object URLs. Keep the supporting passage visible on image failure.
- Review and register the four existing additive migrations, refresh their hash
  manifest, and register the two existing authorized PNG endpoints in OpenAPI
  and the API/UI inventory. No migration was applied in this follow-up.
- Update the routing fixture for the existing native figure-caption retrieval
  route. Source captions remain subject to normal retrieval and verification.
- Refresh bucket presence with a read-only database query. The dated observation
  includes `figure-artifacts`; the old restore result and object counts remain
  recorded. Presence does not establish object integrity or a restore pass.
- Apply repository formatting and patch dependencies that failed the audits.

## Dependency decisions

The audit required `aiohttp` 3.14.4, `certifi` 2026.10.19, and Pillow 13.0.0.
The Pillow pin is updated in both the workspace and parser sandbox; a deployed
sandbox must be rebuilt to receive it. Python 3.11 meets Pillow 13's supported
runtime requirement. The existing Arrow advisory exception is unchanged.

Node tooling now uses Vite 8.2.4 explicitly and overrides Markdown-it to a patched
14.3.3 or newer version. Existing advisory exceptions are unchanged. High-level
audit success does not mean all low and moderate advisories are absent.

References: [aiohttp release](https://github.com/aio-libs/aiohttp/releases/tag/v3.14.4),
[Pillow security and compatibility notes](https://pillow.readthedocs.io/en/stable/releasenotes/13.0.0.html),
[Vite advisory](https://github.com/advisories/GHSA-587h-7wmj-h5pm),
[Markdown-it smartquotes advisory](https://github.com/advisories/GHSA-r7fv-28h4-cvq7),
[Markdown-it reference rendering advisory](https://github.com/advisories/GHSA-gfr2-rv44-r23c).

## Evidence boundaries

The [25-question result](14-checkpoint-failure-repairs.md) belongs to its recorded
Docker image and source fingerprint. Subsequent type, tracing, frontend, manifest,
formatting, and dependency repairs are not a new live 25-question evaluation.
Keep that historical evidence intact. GitHub check results must be read against
the exact pushed commit, and green CI alone does not establish production readiness.

Private checkpoints, credentials, corpus content, and local diagnostic logs stay
outside Git. The immutable phase plan and its outstanding release requirements
are unchanged.
