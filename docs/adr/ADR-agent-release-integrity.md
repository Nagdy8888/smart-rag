---
title: ADR — Immutable verified answer release
status: accepted-for-local-implementation
owner: engineering-lead
last-reviewed: 2026-10-20
approval: User approved executing the review fix plan and adding a test set in this session.
---

# Immutable verified answer release

## Context

The October review reproduced a meaning-changing model rewrite after verification,
paragraph citation remapping, native-block loss, and unchecked draft release after
verification exceptions. The user approved implementing the fix plan. Existing
Phase 6 canonical-evidence and no-uncited-answer requirements remain authoritative.

## Decision

- Keep `organize_answer` as a compatibility graph/SSE stage, but make it an exact
  pass-through. Remove its provider gateway and live prompt binding.
- Preserve final checked text, paragraph/claim identity, and citation mapping.
  Structured frontend rendering owns presentation; it does not need a second
  semantic answer-generation call.
- Release neither an original draft nor a replacement from a later node when
  verification fails. Return a typed citation-free refusal and accurate UI copy.
- Require exactly one verdict per selected verifier link. Missing, duplicate, and
  foreign verdict IDs cannot imply support.
- Route live verifier requests through durable reservation consume and usage
  recording. Account successful but schema-invalid responses, and conservatively
  account uncertain outcomes. Do not retry the verifier.
- Reserve two company answer-stage calls: answer and verifier. Existing route
  maximums and dollar caps are not raised.
- When extra native content exceeds capacity, retain existing checked paragraphs
  and mark the result partial rather than silently evicting those paragraphs.
- Freeze the verifier's payload in the SSE mapper. Later updates cannot replace
  it, and malformed verification cannot fall back to the earlier draft.

## Consequences

Verification failures can produce more honest refusals than the previous unsafe
draft-release behavior. The change does not establish live corpus accuracy; that
requires a full fixed-data comparison with the running API and hosted data.

Historical prompt versions and deprecated binding fields remain readable for
compatibility. They no longer authorize a post-verification model call. Existing
stored historical answers are not rewritten.

This is an agent-release remediation, not acceptance of Phase 6 or completion of
the entire application review plan. Ingestion vision governance, PDF process
isolation, distributed run claims, dependency upgrades, and managed rollout remain
separate work with their own evidence requirements.

## Verification and containment

See the [implementation handoff](../reviews/2026-10-20-comprehensive/12-agent-fix-results.md)
and [synthetic test-set specification](../evaluation/AGENT_RELEASE_TESTSET.md).
If formatting regresses, retain exact checked content. Do not restore the unsafe
rewrite or unchecked-draft exception fallback as a rollback.

## Checkpoint-driven repair follow-up

The same authorized local remediation also preserves unique verifier identities
through a required-key output schema, advances reservation state when a sent
attempt is consumed, and keeps stable logical citation indices across attempts.
Native artifacts must match an explicit request or grounded citation ownership.
Source ordering may emphasize the original question without expanding context.
Arabic vocabulary hints and matching canonical section headings may guide that
presentation, but cannot rewrite retrieval, filter records, or authorize facts.
Specifically scoped ownership drafts may use a matching exact canonical matrix
before verification, preserving the source columns instead of role paraphrases.

Missing explicit question parts and requested category lists may recover bounded
exact text or rows from already fitted canonical evidence. Such recovery does not
restore rejected model prose or authorize another verifier call. Existing checked
paragraphs survive capacity limits; incomplete additions remain partial.

Release retains all owned citation spans. Additional fact-source IDs introduced
by bookkeeping do not authorize synthesized prefix citations. Inference chains
still retain every required source. This preserves the twelve-citation ceiling
without discarding earlier spans from a long code or table claim.

The verifier's provider response uses a closed ASCII reason-code vocabulary.
Support flags and reason codes must agree. Incomplete, filtered, empty, and
refused responses remain fail closed and conservatively accounted; safe failure
codes preserve the provider category without logging raw response content.
This does not add retries or increase the existing verifier output ceiling.

Before model verification, narrowly scoped explicit comparative contradictions
may be rejected deterministically. Ambiguous/negated comparisons still require
semantic verification. Original Python content is checked in full, and native
page continuations require same-version adjacency plus parent-order proof before
restoring function-level indentation. Source syntax errors remain unchanged and
surface as partial results with a signed user-visible warning; quoted code is
compiled for syntax only and never executed.

A requested diagram may share its existing owning paragraph when all prose slots
are occupied. Both its checked link and its paragraph-local citation must own the
same canonical figure chunk. This adds the exact bounded source description and display marker, with a full
owned source span when needed. Checked prose, indices, and earlier spans survive;
all existing character and citation bounds remain enforced.

An empty numbered-figure refusal may recover exact bounded source quotations
when a unique requested diagram and a same-version paragraph explicitly naming
it survive fitting. At least two topical query terms must match. This English-only
copying fallback remains partial, drops the generated conclusion, and adds no
model calls or retrieval. Verification infrastructure failures still fail closed.

BM25 query variants receive bounded scan shares within the existing 300-row
statement, then interleave their own ranks before the authoritative 75-survivor
recheck. Broad heading matches cannot evict an exact identifier before the final
variant balancing stage. This does not relax canonical authorization. A named
Python-function answer must contain the requested definition in a Python block;
unrelated fenced prose is refused before source syntax warnings are signed.

See the [checkpoint diagnosis and live validation](../reviews/2026-10-20-comprehensive/14-checkpoint-failure-repairs.md).
