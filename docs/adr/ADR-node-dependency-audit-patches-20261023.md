# Node dependency audit patches

Date: 2026-10-23. Status: implemented during CI repair.

## Context and change

PR #21's Node audit reported high/critical advisories against Next.js `16.3.8`
and the documentation renderer's transitive DOMPurify `3.4.13`.

- Upgrade Next.js and its paired ESLint configuration to `16.4.1`, covering
  [image optimization](https://github.com/advisories/GHSA-2464-fhr4-w9xw),
  [typed-array cache](https://github.com/advisories/GHSA-673q-mjm6-r5xr), and
  [Server Actions denial of service](https://github.com/advisories/GHSA-p3m5-59mp-jv5r)
  fixes.
- Pin DOMPurify to `3.4.17` through the existing workspace overrides, covering
  [template sanitization](https://github.com/advisories/GHSA-cg2g-xh64-v4q7) and
  [in-place sanitization](https://github.com/advisories/GHSA-mrv2-3pqr-j5jr) fixes.
- Regenerate the shared pnpm lock. Keep React, the package manager, and existing
  audit policy unchanged. Add no advisory ignores and disable no CI checks.

## Verification

Run the repository's high-severity audit policy, frontend lint, types, component
suite, production build, and remote documentation/frontend gate before merge.
Successful dependency auditing is a package-level check; it does not establish
that every advisory was reachable in this application's configuration or that
all deployed services have already been rebuilt.
