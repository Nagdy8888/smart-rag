# Agent excerpt-context repair candidate

## Status and scope

This is a repair candidate on a separate branch. It is not promoted to `main`
and is not a claim of improved live answer accuracy. The hosted Supabase recovery
operation is left unchanged. The live development gate still has ten completed
passes and fifteen questions pending.

The scope is the pre-verification, anchor-gated extractive answer fallback. The
verifier, citation validation, evidence authorization, model budgets, prompts,
retrieval ranking, and post-verification immutability remain unchanged.

## Reproduced defects

Two public-path regressions failed against the existing implementation:

- With query anchors separated by approximately the excerpt size limit, the
  backward scan stopped before reaching the start of the source sentence. A
  synthetic source beginning `It is not true that Orchestration bypasses
  validation.` became `Orchestration bypasses validation.` in the fallback
  draft. This is a pre-verification reproduction, not evidence that the final
  verifier released that answer to a user.
- Case folding can expand a character into multiple characters. Using a match
  position from the case-folded text directly against the original source moved
  the excerpt into an unrelated sentence after a Unicode prefix.

## Candidate fix

Map case-insensitive matches to original source offsets. The common path avoids
allocating an offset map when case folding preserves the source length. Reject
an excerpt when its matching anchors exceed the existing size budget or when
the beginning of its sentence cannot fit. Reapply the existing anchor-strength
gate to the final trimmed excerpt before adding it to a draft.

No new sentence, word, or translated text is manufactured. Every accepted
citation span remains a contiguous original-source substring. An unsafe
addition is omitted while the original draft is preserved.

## Verification and limits

The focused answer-salvage, verifier-scope, and checkpoint-failure tests pass
46 cases, including six new boundary/Unicode/control cases. Strict type checking,
Ruff, and formatting pass for changed files.

An offline replay used archived evidence from the ten completed development
questions and a synthetic initial draft. Six fallback outputs changed; every
newly attached citation span remained source-exact. This exercises excerpt
construction only: it is not a provider run, a complete pipeline evaluation,
an ACL revalidation, or a new live pass score. Those output changes require
review in the eventual full live gate.

The complete unit/contract results and draft-branch checks are recorded after
they finish. Promotion remains blocked on the full answer-quality regression
gate against the final candidate and unchanged test criteria. No historical
messages, checkpoints, or documents are rewritten by this code change.
