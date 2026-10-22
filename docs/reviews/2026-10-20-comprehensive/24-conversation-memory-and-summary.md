# Connected chat memory and automatic summarization

## Current target profile

The user selected `gpt-6-luna` for every chat role, and the configured provider's
model inventory was checked for that exact ID. Runtime pins and the example
environment now match. The embedding model and native corpus assets are
unchanged. The latest 50-turn, single-conversation evaluation stopped after 34 completed
turns; earlier mixed-model results below remain historical evidence.

Luna summaries and verification use low reasoning effort within the existing
output caps and timeouts. A real all-Luna diagnostic demonstrated summary writes;
its verifier timeout prompted the current bounded verification setting. LightRAG
also now keeps its qualified local tokenizer independent of the provider model
alias, resolving an all-Luna startup failure without changing stored graph chunks.

## Latest all-Luna validation status

The v9 conversation completed 34 turns. Two answers failed: m22 asserted a
relative speed ranking where the source supplied properties, and m26 retrieved
only one topic in a resolved comparison follow-up. Memory recalls, requested code,
source figures, and the tested multi-page table passed the checks completed so far.
This is not a 50/50 result or a complete semantic quality pass.

Turn 35 was not admitted: API logs show HTTP 429 followed by HTTP 402. The local
monthly budget ledger contains $96.545895 committed across 562 query reservations
against a $100 configured cap. Unknown Luna pricing is conservatively charged at
per-call caps, so that ledger is not a confirmed provider invoice. No budget cap
was increased and no historical accounting or failed evaluation was deleted.

The evaluator now skips message/citation/checkpoint lookup when admission returns
no run ID and records the admission HTTP status instead of crashing on
`/runs//citations`. Prompt `answer_v20` requests source-supported properties without
unsupported relative rankings. A bounded routing fallback splits an accepted
resolved ?How does that differ from ??? rewrite into its two existing topics;
both branches retain the same authorization, run, and reservation. These changes
still need a new paid end-to-end evaluation when budget permits.

After these changes, the full Python unit suite passed: 2,191 passed and four
skipped. Full Pyright reported zero errors. Ruff lint and formatting passed for
the changed routing and evaluator files. The running API reports ready. These
offline checks do not substitute for the incomplete live conversation test.

## Implemented behavior

The agent now summarizes older turns before constructing its next prompt. It
keeps the four newest messages verbatim and a compact summary of older user
preferences, corrections, and discussion topics. A summary starts at eight
messages or 6,000 characters; memory passed to answer generation stays within
8,000 characters. Summaries are limited to 1,400 characters and have an explicit
message watermark so the same prefix is not summarized repeatedly.

The summary lives in a company/user/conversation namespace. It is untrusted
conversation context, never evidence for company facts. Grounded answers still
require authorized source passages and normal citation verification. Later user
corrections take precedence over old preferences.

Explicit user remember/update statements have an additional deterministic safety
net: the initial setup and the two latest corrections are stored as exact user
text, at most 200 characters each. Assistant assertions, questions, credentials,
code, links, and source markers are excluded. This local preservation can run
when summarization is deferred; it does not advance the summary watermark or
consume a model call. Statements remain untrusted conversation context and cannot
authorize access or support company-document claims.

Summary generation uses the pinned `summary_v3` prompt, the existing model
gateway, strict structured output, one counted reservation consume, and a
six-second maximum. It runs only with call and deadline headroom. Failure retains
the previous summary and bounded recent messages, without claiming compaction.
Checkpoint state records `written`, `deferred`, or `not_needed`.

## Defects found in live testing

- The former post-answer summary hook supplied no messages and wrote a placeholder.
  The real path now runs before profile and answer generation.
- Grounded company answers did not receive conversational memory. They now receive
  bounded context solely to resolve references and presentation preferences.
- Answer formatting clipped every memory record to 500 characters. A valid saved
  reviewer requirement near the end of a summary therefore vanished from the
  model input. Complete summaries and the newest complete messages now survive.
- Retrieval reserved model-call slots but could consume all prompt-token holds,
  leaving verification unavailable despite relevant retrieved evidence. It now
  preserves answer plus verifier token/USD holds and uses deterministic ranking
  when optional reranking cannot fit.
- A retrieval provider failure could leave an old optimistic reservation version
  in the shared ledger. The consume callback updates balances before provider
  work, including failed attempts.
- Corrective retrieval updated its ledger but dropped that ledger's reservation
  version before answer generation. Both successful corrections and retrieval
  error paths now propagate version, balances, call count, and token usage.
- The same PDF code continuation could arrive through its parent and child with
  different base indentation. These copies now count as one candidate when the
  exact signature and body agree. Different source statements remain ambiguous.
- A named table caption could arrive without rows on its continuation page.
  Bounded companion loading rechecks caption and row access through the existing
  authorization RPC; source fragments retain their individual citations.

## Reproducible development test

`tests/fixtures/query-memory-linked50-v4.json` contains 50 connected turns. It
uses one conversation through the normal authenticated API/SSE flow. The project
nickname and reviewer requirement are recalled repeatedly; turn 20 changes the
requirement from seven to nine. Company questions cover prose, tables, figures,
code, explanations, Arabic, security, and one expected unsupported-fact refusal.

Run `scripts/eval_conversation_memory.py` with local authentication and a fresh
private output directory. Credentials are supplied through environment variables
and are never written to the report. The runner records dataset hash, source
fingerprint, conversation/run IDs, persisted answers, citations, summary status,
verifier reason codes, and per-question terminal progress.

The checks cover persistence, recall, grounding availability, requested language,
format, and Python syntax. They are development checks, not an independent semantic
judge. A cited answer about the wrong topic is still a failure on manual review.
The earlier independent 50-question benchmark and all partial runs are retained.

Version 2 remains available. Version 3 replaces a question about the absent
`ToolValidationError` identifier with a question about tool input validation.
Searching the canonical uploaded book found no occurrence of that identifier;
the agent must not invent a definition to satisfy a faulty positive test.
Version 4 retains all version-3 questions and tightens two relevance checks:
input validation must remain the comparison subject, and RACI answers must name
the operational teams rather than a neighboring agent-role taxonomy.

## Release evidence

The completed version-4 candidate ran all 50 turns in one conversation: 40 passed
the development checks and 10 answer checks failed. Every preference recall
passed, including Arabic recall, the corrected count of nine, and the final
language preference. There were 23 summary writes. This result is preserved in
`.private-eval/connected-memory50-v4-20261022/`.

The subsequent 13-turn diagnostic passed 9 checks. It confirmed complete
two-page Table 2-1 reproduction, but exposed code indentation ambiguity and a
lost initial preference in that shorter conversation. A cited Arabic explanation
also requires semantic review; format and citation presence alone do not prove
correctness. Diagnostic results are preserved rather than relabeled as a full run.

The completed version-5 candidate used fixture version 3 and passed 44/50 basic
checks in one conversation, with 23 summary writes. Every preference recall
passed, including Arabic, the corrected reviewer count, and final language
recall. The six automated failures were m12, m19, m21, m31, m35, and m47.
Manual review additionally found wrong-topic answers at m26, m36, and m44, plus
unrelated appended native snippets at m17 and m28. Thus 44/50 is not a semantic
accuracy score. Full results remain in
`.private-eval/connected-memory50-v5-20261022/`.

The next candidate fixes ranking to use resolved references while preserving
original-first candidate search. Rank-cache keys now include profile context,
preventing identical follow-up wording from reusing another subject's ranks.
Arabic/mixed questions may use the same single counted preparation call for an
English search rewrite. No filters, authorization rules, or coverage thresholds
are relaxed. The immutable prompt is now `query_profile_v3`.

Code explanations may use a bounded, exact introductory source paragraph before
verification when a generation omitted it. Repeated bold field/value records
can become complete Markdown tables without guessing cells. Unrequested code
and table bodies are no longer appended merely because their source was cited;
images remain automatic when their evidence is used. Figure captions exclude
preceding PDF code comments while retaining exact source substrings.

The 18-turn diagnostic passed 14 development checks. A subsequent nine-turn
diagnostic confirmed the resolved S3 follow-up and repeated figure reference,
but still exposed an Arabic heading followed by an English table and incorrect
tool-validation subject matter. These failures remain in their original reports.

A controlled local comparison uses `gpt-4.1-mini` for answering and verification,
with `gpt-4o-mini` retained for preparation, ranking, and summaries. The four-turn
comparison passed the earlier basic checks, but manual review rejected its
untranslated table. The Arabic-table check now requires substantial Arabic inside
the actual table rows. Requested source-backed tables also use a structured-output
pattern requiring a header, separator, and data row; `answer_v18` explicitly asks
for the translated table. Canonical English tables are not appended when a cited
paragraph already contains the generated table. The stricter two-turn diagnostic
passed both checks and manual inspection confirmed translated cells.

Summary models have an independent role pin, so an answer-only model override
does not disable summarization. Usage pricing recognizes both configured model
families; unknown model prices conservatively retain the reserved cost rather
than being charged at another model's lower rate. Budget ceilings, authorization,
and verification thresholds remain unchanged.

Latest local checks: 2,170 Python unit tests passed, four skipped; Python types,
Ruff lint, and formatting passed. The preceding contract run passed 300 tests,
with 257 environment-dependent cases skipped; a current contract run is pending.
The authenticated browser suite passed 42/42. Frontend types, 737 unit tests, and
production build passed. The plain frontend-tier invocation lacked live
credentials; its authenticated coverage is established by the separate
credentialed browser run. A fresh full 50-turn candidate is running with fixture
version 4. These are local results, not hosted recovery or a production-readiness
claim. No changes have been committed or merged yet.

The version-6 candidate completed all 50 turns with 47 passing development checks
and 23 summary writes. Its failures were Arabic preference recall at m37 and
language recall at m49/m50. Checkpoint inspection found the nickname and corrected
count present at m37, while the general answer ignored them. A temporary Arabic
answer request had also overwritten the English-by-default preference. The raw
run remains in `.private-eval/connected-memory50-v6-20261022/`.

`general_chat_v3` explicitly permits recalling user-provided details from bounded
memory while keeping company evidence and authorization separate. `summary_v4`
distinguishes temporary formatting from lasting preferences. A deterministic
language-update guard requires a quoted ongoing preference and rejects a local
answer request. Regression tests cover one-turn Arabic, a local request using
"prefer", and an intentional ongoing language change. All 50 focused tests pass;
a fresh full candidate is required before reporting the final result.

The version-7 candidate was interrupted after 16 turns when m03 produced a
one-sided knowledge-versus-memory comparison. Its partial results are retained;
it is not a completed 50-turn score. A new pre-verification coverage helper can
copy one exact fitted-source sentence for an omitted comparison side. It does
not run after verification or add a model call, and preserves existing limits.

The following eight-turn diagnostic passed seven basic checks, but m36's
unsupported causal explanation was rejected. Manual review additionally rejected
m50 for inventing another reviewer correction. The numeral-presence checker had
missed that contradiction and now has a regression test for it. The actual
semantic review therefore accepted six of those eight answers.

The user subsequently required GPT-4o mini for budget reasons. The GPT-5.4 mini
comparison was stopped; answer and verifier overrides were restored to
`gpt-4o-mini`. Summaries, preparation, and ranking also use GPT-4o mini. Prior
higher-model scores are historical comparisons, not evidence for this restored
profile. A fresh diagnostic is running before another full conversation.

## 2026-10-23 save-point status

The user chose to retain the $100 local monthly cap and then requested a commit
and push of the current work. The existing conversation and all private evaluation
artifacts are preserved. The next question remains m35. No 50/50 result, hosted
Supabase recovery, or production readiness is claimed. The continuation runner can
resume the same conversation into a new output folder and stops on admission
failure without sending the remaining turns.
