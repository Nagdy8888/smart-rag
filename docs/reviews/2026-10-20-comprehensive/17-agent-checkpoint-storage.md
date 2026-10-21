# Agent checkpoint storage repair

## Observed defect

The synchronous and asynchronous query savers compacted pending channel writes
only when the channel value was a mapping. `branch_results` is a list, so its
nested canonical `citation_text` fields bypassed the existing source-body
compactor. Full checkpoint channel values already traversed nested sequences;
the pending-write boundary behaved differently.

A read-only inspection of the locally restored checkpoint backup found
509,828,269 bytes of serialized `branch_results` pending-write payload across
20,246 rows. This measures payload bytes, not reclaimable physical table space.
It identifies a contributor to database growth, not the sole cause of the
hosted outage.

## Change

Both saver paths now pass every pending value through the existing recursive
compactor inside a temporary wrapper. Mapping, list, and tuple values receive
the same treatment. Source bodies become the existing hashes and character
counts; passage IDs and other state metadata remain available. Write order,
duplicate channel entries, scalar values, task IDs, and task paths are retained.

Compaction creates a separate persistence value. In-memory source evidence used
by answer generation is unchanged. There is no automatic historical deletion,
new retention policy, schema migration, model call, or answer-policy change.

## Verification

- Before the fix, four new regression cases failed: list and tuple values on
  each saver path. Mapping controls passed.
- After the fix, all six new saver-boundary cases passed. They check source-body
  removal, evidence metadata, serialization, size reduction, order, duplicate
  channels, scalar values, and absence of in-memory mutation.
- The focused checkpoint and conversation-deletion run passed 11 tests.
- Changed Python files passed strict type checking, Ruff, and format checks.
- An offline replay of 500 archived retrieval writes reduced serialized payload
  from 12,561,456 to 5,291,312 bytes (57.88%), preserving inspected evidence IDs
  and replacing source text with hashes/counts. All 3,330 inspected evidence
  records retained chunk, document, version IDs and non-source metadata.
  This is a fixed sample by primary
  key order, not an estimate of whole-database savings or a live answer score.

- The clean-checkout unit suite passed 2,100 tests and skipped four, with nine
  existing warnings. The initial workspace run passed 2,098 tests but two CLI
  tests discovered a private local ingest identity and attempted to contact the
  unavailable hosted database. No assertions were weakened: the same complete
  suite passed from a clean checkout without private runtime artifacts.
- Full strict Python type checking passed with zero errors and warnings; the two
  offline pinned-library/runtime-setup contract checks passed.

Remote checks must be verified against the resulting commit.
Hosted resume, new writes, and the remaining live answer gate cannot currently
be verified: the Supabase free-plan recovery remains a separate operation.
The previously completed final live batch contains 10 passing questions out of
25 planned; it does not establish a 25/25 result. No phase is closed by this
repair.
