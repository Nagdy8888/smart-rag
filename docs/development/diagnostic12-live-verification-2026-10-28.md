# Twelve-question live verification — October 28, 2026

This is a development rerun of exactly the twelve previously flagged cases,
following [the repair pass](diagnostic12-repairs-2026-10-28.md). It is not a
holdout evaluation, production approval, or evidence that all twelve now pass.

## Scope and actual results

The launcher submitted seven company questions and five Web questions, once
each. Both conversations and all twelve assistant responses are available
through the authenticated conversation-history API. No additional paid question
round was sent after examining these results.

- **Seven complete answers:** company m23, m31, m46; Web w01, w04, w05, w15.
- **Three partial answers:** company m21 and m38; Web w07.
- **Two inconclusive context replays:** company m12 and m19. Both refused rather
  than releasing unsupported answers. Their database run status is `partial`;
  that operational status does not make them successful substantive answers.
- **Zero operationally failed or cancelled runs.** This is distinct from answer
  completeness and correctness.

The company automated check passed 5/7. The Web automated check passed 5/5,
but inspection found w07 incomplete. Those checks are insufficient to establish
semantic success. The reviewed results above take precedence over that pass count.

### Company cases

- **m12 / m19:** the replay prepended only the immediately preceding user
  question. Those preceding questions were themselves referential. The original
  named table/figure antecedents were missing. This was a diagnostic-harness
  mistake, not valid evidence that the application failed a correctly restored
  conversation. Corrected packs now include m10+m11 and m17+m18 respectively;
  their standalone anchors are checked, but neither replacement was submitted.
  The original rerun inputs and results remain unchanged.
- **m21:** the timeout did not recur. The verifier supported the archetype list,
  reflex description and plan-execute/query-decomposition explanation. It
  rejected two broader compound descriptions, so the released answer remained
  partial. Complete coverage of all archetype descriptions is not established.
- **m23:** completed with supported checkpoint/persistence explanation; the
  prior operational deadlock did not recur in this request. The separate
  two-connection database test remains the reproducible lock-order evidence.
- **m31:** completed with the requested cited code and explanation.
- **m38:** the figure-availability guard rejected a false image-unavailable
  claim. The supported figure description and original-image marker survived.
  The released answer remained partial. A marker in a saved answer is not a
  fresh browser verification that its original image rendered.
- **m46:** completed with cited security explanation/table; the prior answer
  timeout did not recur.

### Web cases

- **w01 / w04:** completed with the RFC rate-limit and no-cache requirements.
- **w05:** completed in Arabic with the optional Retry-After distinction.
- **w07:** correctly gave the two target sizes and one conformance level, but
  explicitly could not establish the other level from the stored excerpts.
- **w15:** completed with the PostgreSQL isolation/phantom distinction.

## Fix after the live run

w07's stored provider excerpt omitted a heading containing the missing level.
The value was absent before prompt fitting, so changing a prompt window alone
would not repair it. The Web executor now allows its existing crawl fallback
to read a nonempty candidate when a requested numbered criterion lacks explicit
conformance-level evidence.

The trigger uses requested references and observed metadata, not an expected
answer. Only an existing current-run allowed candidate whose title names the
missing reference may be refreshed. Another reference ends the metadata window.
The existing five-operation ceiling still applies, and an optional refresh is
skipped with less than twenty seconds remaining. There is no additional search
round, model call, company-to-Web fallback, or authority inference.

Real fetched page text replaces the provider excerpt only when requested-field
coverage improves. Failed/unhelpful refreshes retain the original evidence and
normal verification can still return a partial answer. Existing source rows,
historical answers and checkpoints were not rewritten.

A public-page-only live probe through the running app crawl proxy fetched the
same stored W3C candidate URL. The original evidence had one missing reference;
adding the fetched text removed that gap. This used **zero model calls and zero
additional agent questions**. It validates page extraction, not post-fix answer
generation: w07 has not been submitted to the agent again.

## Validation and current local state

- Full Python unit tier after the new fix: **2,320 passed, 4 skipped**.
- Focused Web graph/diagnostic tier: **40 passed**.
- Explicit isolated database contracts: **38 passed**, including lock order,
  citation authorization, conversation privacy, admission and budget settlement.
- Ruff lint/format and strict Pyright passed.
- The local API was restarted after confirming no active runs. Readiness and
  authenticated histories were checked again after restart.
- No frontend files changed in this post-rerun fix; earlier frontend/browser
  evidence remains separately documented. No fresh visual pass is claimed here.
- All changes remain local; no commit, push or hosted deployment was performed.

The temporary company/test-account limits were raised to **$150** for this
finite rerun, then restored to their original **$100**. Ledger accounting rose
from **$123.029888** to **$131.030197**, a delta of **$8.000309**, largely from
safety allowances. These are recorded accounting values, **not provider-billed
charges**. Restoring limits does not erase usage; ordinary budget admission can
therefore remain blocked. No further agent requests were made to bypass that.

Private evidence remains gitignored under `.private-eval/`: the two
`reverify12-*-20261028T*` result/checkpoint directories, budget lease, final
authenticated audit, corrected-context proof, public crawl-proxy heading fetch,
and explicit database-contract output. No sensitive passages or credentials
are included in this report.
