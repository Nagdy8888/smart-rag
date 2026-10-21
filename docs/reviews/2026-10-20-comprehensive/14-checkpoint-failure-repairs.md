# Checkpoint diagnosis and live agent repairs

Started: 20 October 2026. Continued: 21 October 2026.
This follows the [real app-flow run](13-live-user-flow-results.md).
The user authorized reading the failed LangGraph checkpoints, repairing their
causes, and continuing until the same 25 questions pass their development checks.

## Evidence and scoring boundary

The diagnostic reads use a read-only Supabase/PostgreSQL transaction. Node order
comes from `langgraph.checkpoint_writes`, rather than the last terminal node or
empty checkpoint metadata. Fitted evidence was reconstructed from canonical chunks
and checked against the stored length and hash; all 25 original runs matched.
Raw source passages, prompts, answers, checkpoint payloads, and credentials remain
outside these review documents, under gitignored `.private-eval/`.

The 25 questions and acceptance checks were frozen before the first full repaired
run. They cover eight prose, six code, six table, and five figure questions, with
four Arabic prompts. Checks require the requested facts/artifacts, full requested
function operations or table rows, appropriate language, persisted citations,
and persisted/streamed text parity. A completed terminal alone is not a pass.
These are known development topics, not an unseen holdout or independent accuracy
measurement. A partial terminal can pass these checks if the requested content
and the other checks are satisfied; that does not turn its status into complete.
Manual review checks requested main facts/artifacts, source fidelity, and clear
contradictions. It is not independent SME validation of every background sentence.

The original valid run scores **6/25**, and the first full repaired run scores
**19/25**, under the same checks. Later targeted diagnostics are not pooled into
a full-run score. The final single-build run passes **25/25 fixed development
checks: 20 completed and five partial**. This does not mean 25 fully verified
answers or general 100% accuracy. See the final evidence below.

The first citation-count collector read the conversation message's inline
`citations` array, which is intentionally empty. The app fetches citations from
`GET /runs/{run_id}/citations`. Saved responses were rescored using that endpoint
without resubmission or changing the content criteria. The resulting private
`*-scored.json` files supersede the invalid zero-citation instrumentation result.
The six original verification refusals really had zero persisted citations.

## Final single-build validation - 21 October 2026

The guarded aggregate export is
[checkpoint-repair-validation.json](evidence/checkpoint-repair-validation.json).
It rejects an incomplete run, mixed builds, changed input/criteria, missing manual
reviews, unmatched source lines, unavailable figures, or changed production files.
The final evidence is from `answers-round15.json` and `round18-image.json`, with
local API image `e0a268f2b34fc5107d8ba5ada6ad901e1e195f446d34290b5acf624ea8010f39`.
Earlier failed candidates remain private and are not pooled into this result.

- **25/25** original fixed checks pass across eight prose, six code, six table,
  and five figure questions. The supplemental source-aware code gate passes 6/6.
- **20 verified/completed; five verified-partial/partial.** The partial cases are
  `live-23`, `live-22`, `live-14`, `live-07`, and `live-02`. Their partial status is
  preserved; it is not promoted to complete by the evaluation scorer.
- All **25** saved answers match the actual streamed text and have at least one
  available persisted citation. This is not a claim that every individual
  citation or background sentence has independent SME approval.
- All **25** fitted evidence sets match their checkpoint text hashes. All **16**
  code/table-containing answers pass displayed-line comparisons against fitted
  canonical text. Scoped manual source reviews cover all 25 main requests.
- All **five** requested figure endpoints return valid PNGs. Their hashes match
  the files visually inspected for the architecture, autonomy slider, embeddings,
  n8n workflow, and query-orchestration diagrams.
- **Five** code examples pass syntax compilation without execution. The sixth
  preserves a confirmed syntax error in the original PDF and emits
  `source_code_syntax_invalid`. Its exact original code hash and required warning
  were frozen in supplemental criteria v2 before its first final live use.

The final 25 runs have 25 ledger rows each for answer, verifier, rerank, and query
embedding operations. Their stored ledger amount is **$0.060036**, with 345,884
prompt tokens and 13,611 completion tokens. This is the recorded amount for this
final run only, not invoice reconciliation or the cost of all earlier candidates.

Runner elapsed time, including conversation creation plus message admission and
SSE, has median **24.14 s**, nearest-rank p95 **90.09 s**, and maximum **90.78 s**.
The two long totals include about 63 seconds before the timed message operation;
the recorded timings do not establish the cause of that earlier wait. Message
admission plus SSE has median **22.078 s**, p95 **27.125 s**, and maximum **27.265 s**.
SSE-only median/p95/max are **19.312 / 23.734 / 24.453 s**. History/citation readback
is outside these timing fields. These observations do not certify production
latency, concurrency, or the staging streaming gate.

The latest full Python unit run is **2,083 passed, two existing failures, four
skipped**. Pyright retains **96 existing errors**. Ruff passes for all **74** changed
authored Python files; `git diff --check` passes. The remaining architecture and
frontend-lint blockers below still apply. **This checkout is not release-ready.**

## Where the failures occurred

- **Verifier response identity:** four original refusals contained missing,
  duplicated, or mismatched verdict identities. This was an output-contract
  failure, not evidence that every answer claim lacked support.
  A later six-claim comparison had `verifier_incomplete` and correctly withheld
  its draft. The old adapter collapsed incomplete status and empty output into
  that single code, so the exact provider cause cannot be recovered from its
  checkpoint. It is not established that this was token truncation.
- **Uncertain provider outcomes and reservation state:** gateway exceptions
  obscured the actual failure class. A later traced timeout also exposed a stale
  optimistic reservation version on the next answer/verifier operation.
- **Code intent and selection:** identifiers before words such as implementation
  were not recognized as named-code requests. A page-ending signature could also
  outrank its full function body. Extracting only one citation-sized slice cut
  longer functions, while permissive boundaries included example harness code.
  Manual review later found a complete-but-invalid function: a PDF page break
  separated its signature from a native continuation whose base indentation had
  been removed. Another example has a missing string delimiter in the original
  PDF itself, confirmed using its authorized cited-page image. That original
  error must not be silently changed when the user requests unchanged code.
- **Table and artifact selection:** caption-only evidence could tie real rows;
  tables spanning stored page layouts lost continuation rows. Native attachment
  included unrelated retrieved figures, tables, or whole code listings.
- **Question scope and completeness:** relevant passages were present, but the
  answer substituted a neighboring role taxonomy or omitted the second part of
  a question. The verifier correctly removed some unsupported generated claims.
  Releasing those claims unchecked would conceal the generation problem.
  Later manual review caught a completed answer reversing an explicit tradeoff
  direction; the existing model verifier had accepted it. That candidate was
  rejected despite passing the frozen keyword checks.
- **Artifact capacity:** one Arabic run filled all six paragraph slots with
  prose and could not append the requested category matrix. The provider schema
  now reserves half of those slots when that classification request and a fitted
  category-table header match. Table recovery runs before generic anchor fill.
- **Figure placement at capacity:** a later run passed 20 questions, then described
  the correct architecture diagram without displaying it. The diagram and its
  citation survived retrieval and verification, but all six prose slots were
  occupied. A figure and its exact bounded source description may now share the paragraph
  that already owns its canonical
  chunk through both a checked link and a citation. The full description receives an exact owned citation when needed. No prose is
  evicted, no
  paragraph/citation/character ceiling increases, and unrelated numbered figures
  remain excluded. Replay of the failed checkpoint preserves all six paragraphs,
  includes the requested diagram, and is idempotent. The failed run is retained;
  subsequent candidates were tested independently. Another candidate displayed the diagram
  but named only its central component. That candidate was rejected for missing
  component names; retaining the full source description closes that omission.
- **Numbered-figure refusal recovery:** a later candidate returned a refusal for
  semantic tool embeddings even though the exact requested figure and supporting
  prose survived retrieval. Its generated claim was rejected by the verifier;
  the checkpoint does not retain a more specific semantic rejection reason.
  A narrow English-only fallback can quote a unique numbered figure plus a
  same-version explanatory paragraph explicitly referring to it and matching
  at least two topical query terms. It requires exact bounded source spans,
  remains partial, and never restores the rejected model claim or conclusion.
  The saved-checkpoint replay proves exact claims/citations and idempotence.
- **Exact identifier loss during degraded retrieval:** a later candidate passed
  17 questions before returning unrelated fenced prose for a requested function.
  The checkpoint records dense timeout, an empty term channel, and BM25 results
  dominated by broad heading matches. The exact function identifier was correctly
  recognized. A real read-only scan showed its body hits fell outside the first
  75 unique IDs under the old cross-variant ordering, before authoritative recheck
  and final variant balancing. Each variant is now bounded within the existing
  300-row total, then its ranks are interleaved before recheck. The real pinned
  `pg_search 0.25.2` probe changes first-75 definition recall from zero to one
  while returning 155 rows. No raw score is compared across query variants, and
  canonical authorization, the 75-survivor cap, and final max-per-variant RRF stay
  unchanged. A separate structural release guard refuses unrelated prose or a
  different function instead of signing it as an original source syntax error.
  The subsequent real app run retains an authorized BM25 definition candidate,
  fits the full requested function, and passes source/syntax checks. The scan
  comparison is a pre-authorization boundary test, not a substitute for that live
  authorization proof. [ParadeDB ranking documentation](https://www.paradedb.com/learn/search-concepts/reciprocal-rank-fusion)
  explains why independent rankings use rank contributions rather than comparing
  unrelated score scales.
- **Language:** the original Arabic question survived in checkpoints, but the
  provider request serialized it as literal Unicode escapes and lacked an
  explicit presentation-language field. Arabic explanations subsequently worked
  with literal Unicode, an explicit language choice, and the updated prompt.
  A later Arabic role question still failed because its single generated claim
  cited broad introductions rather than the retrieved responsibility passage;
  verification correctly refused it. Source presentation had extracted only
  Latin tokens, assigning no topic coverage to the Arabic question.
- **Citation retries:** skipping one unresolved citation could let a later
  citation take its logical index. A retry could then conflict with that stored
  index, preventing otherwise valid claim-local recovery.
- **Release-time citation expansion:** a later monitoring run passed verification
  but failed persistence. Twelve citation rows were stored before a further
  insertion exceeded the cap. The draft had ten citations; release rebuilt
  additional prefix citations from bookkeeping source IDs. Its source/link-keyed
  dictionary also discarded earlier spans when one claim cited the same chunk
  twice. Replaying that failed payload after the repair retains ten citations.
- **Role assignment semantics:** a later candidate passed the frozen keyword
  checks but manual review found that a prose sentence assigned infrastructure
  efficiency monitoring to ML engineers. The canonical ownership matrix assigns
  it to Infra/SRE. That candidate was stopped and preserved as a rejected attempt;
  a keyword pass was not accepted as evidence of correct role ownership.

## Implemented repairs

- The strict verifier schema requires each selected link as a unique required
  object key. The adapter checks the exact key set and preserves false verdicts.
  Missing or foreign identities still fail closed. Only sources cited by the
  selected links enter that verifier request.
  The current provider contract uses a closed set of short ASCII reason codes
  instead of free-text explanations; contradictory support/reason pairs fail
  closed. Incomplete-response metadata now distinguishes output-limit and
  content-filter failures, and completed empty output distinguishes refusal
  from an unexplained empty response. Only allow-listed codes reach checkpoints.
  The 1,000-token verifier ceiling and one-call limit remain unchanged.
- Answer reservation snapshots advance immediately after consume, including
  failed sent attempts. Received invalid output and uncertain sent outcomes are
  conservatively accounted. Stable error codes replace generic exception names.
  The verifier still runs at most once; existing route and dollar caps remain.
- Named-code recognition supports either word order. Selection prefers a body
  over a lone signature. Longer fitting functions use two exact bounded citation
  spans, with existing claim limits and truthful partial status beyond capacity.
  A page-break join can restore only the function-level indentation when native
  fragments share a document version, section, and consecutive physical pages,
  and a fitted parent proves their order with only footer/blank lines between.
  The statements and internal indentation remain unchanged, both fragments gain
  exact citations, and the result must parse as one function. Ambiguous joins,
  different scopes/versions/pages, prose gaps, and trailing harness code fail.
  Replaying the failed example produces valid syntax with exact citations to
  both physical pages, without model calls or canonical document writes.
- Named Python examples also receive a syntax-only compilation check, without
  execution or source imports. An invalid source example is reproduced intact,
  marked partial, and emits `source_code_syntax_invalid` with a user-visible
  warning. This is a source-quality limitation, not a successful code repair.
- Native selection follows exact requested artifact numbers or checked citation
  ownership. Complete canonical table rows are packed across layout headers and
  footers; neighboring artifacts are excluded. Existing checked paragraphs cannot
  be evicted to make room.
- Already fitted source records are presented by coverage of the original
  question. This changes their order, not their content, authorization, ranks,
  count, or input size.
  Arabic literal matching and a bounded agent-domain vocabulary glossary also
  support English evidence for Arabic questions. Canonical section coverage
  breaks equal body-coverage ties. These are presentation hints, not retrieval
  rewrites, answer templates, authorization decisions, or a general translator.
- Specifically scoped responsibility questions can shape an unverified draft as
  the exact canonical RACI matrix when that source matches every specific scope
  term. This removes generated role paraphrases before verification, preserves
  the original column assignments, and excludes duplicate native-table display.
  Generic role questions and unrelated scopes do not trigger this shaping.
  A subsequent live replay exposed duplicated continuation rows. The shaper now
  prefers the fullest matching fitted matrix, and coverage does not append a
  second copied table. Both rejected candidates are retained privately.
  It never replaces a verified answer and adds no model calls or retrieval.
- Bounded coverage fallback can copy an exact fitted paragraph for a missing
  explicit second question part. Relevant cited responsibility tables, or a
  category table whose header matches an explicit classification request, can
  retain all fitting rows. The fallback adds exact evidence and citations; it
  does not restore rejected model prose. Capacity omissions remain partial.
- A narrow deterministic check rejects unambiguous opposite comparative
  directions for the same explicitly named canonical topic before model
  verification. Negation, mixed comparator contexts, unnamed scope, and
  inference links defer to the semantic verifier. This is not general NLI.
  The actual failed claim replay removes the contradiction and retains five
  other links. Updated prompt versions also require preserving predicate
  direction, entity ownership, and overall versus local scope.
- Unicode remains literal in company answer, verifier, query-profile, and rerank
  requests. The answer request explicitly identifies the requested language.
  Historical prompt versions remain intact; current answer/verifier versions are
  `answer_v11` and `verifier_v5`.
- Citation indices are assigned from the logical input sequence before attempts.
  Retrying a failed citation cannot take a later successful citation's slot.
  Claim-local repair preserves successfully persisted citations.
- Release preserves every owned span, including multiple spans from the same
  chunk, instead of synthesizing extra fact citations for bookkeeping holders.
  Inference links continue to retain all required relationship sources. Tests
  cover six claims with twelve owned citations, two spans in one source, and
  multi-source inference preservation.
- Category-matrix generation has a strict three-prose-claim limit within the
  existing six-paragraph ceiling. Binding retains at most two owned citations
  per claim. These reservations leave room for exact table rows instead of
  raising output, citation, model-call, or dollar caps.
- SSE preserves the verification-unavailable reason and the immutable checked
  answer. There is no post-verification model rewrite or draft-release fallback.

## Validation and private reproduction

Mechanism tests use synthetic evidence and fake provider boundaries. They cover
strict verifier identities, false verdicts, reservation versions after timeout,
complete code versus signatures, exact function spans, table continuation rows,
artifact relevance and capacity, exact numbered-figure refusal recovery,
pre-recheck BM25 variant fairness, requested-code identity, Unicode input,
source-order preservation, missing facets,
cited-table containment, capacity behavior, and citation retry positions.

Private working directory:
`.private-eval/runs/agent-live25-checkpoint-repair-2026-10-20/`.

- `questions.json`, `acceptance-v1.json`: frozen development input and criteria.
- `baseline-results-scored.json`, `answers-round1-scored.json`: corrected original
  and first full repaired scores.
- `live-NN.json`, `live-NN-fusion.json`: original per-node diagnosis and
  hash-checked canonical evidence reconstruction.
- `targeted-round*-stages/`: later stage snapshots for remaining failures.
- `round*-image.json`: tested image and source/question fingerprints.
- `terminal-*.txt`, `answers-*.json`: visible question/stage/answer transcripts
  and actual authenticated API/SSE responses.

The runner signs in with the existing private evaluator account and creates a
fresh conversation per question. It uses the app's message, streaming, history,
and citation endpoints with live retrieval and providers. This is app-protocol
coverage; it is not a browser-click or hosted-deployment certification.

Remaining repository-wide checks are tracked separately. The latest full unit run
has **2,083 passed, two failed, and four skipped**. The two existing failures concern
direct figure-provider tracing and an older routing-plan snapshot. Pyright still
reports **96 errors**. The architecture scanner
still reports an unchanged 602-line retrieval module against its 600-line cap.
These are release blockers, not passes hidden by the 25-question development set.
The frontend has **700 passing tests**, and its typecheck and production build
pass. Full frontend lint still reports **two errors and four warnings** in
unchanged citation/image/test files; lint of the changed warning-copy files passes.
Intermediate runs also had two Supabase DNS failures and one three-second
structured-table process deadline failure. Those cases passed isolated checks and
the latest full suite. The original failing logs are retained; no deadline or
security bound was relaxed.

Figure verification additionally fetches all five image bytes through the same
authenticated `/figures/{id}` endpoint used by the frontend and visually inspects
the resulting PNGs. Separate immediate-after-login probes received HTTP 401 responses;
their failing artifacts are retained. A subsequent authenticated conversation/figure read and
a repeat of all five image reads succeeded with HTTP 200. No authentication or ACL
check was bypassed or relaxed. The original probe did not retain enough detail to
establish the cause of those intermittent 401 responses. The final successful probe used
normal bearer authentication, recorded every read attempt, and returned HTTP 200
for all five figures on its first attempts.

Content checks do not execute the reproduced code examples or independently
certify every source-document layout detail. Exact copying of stored canonical
text is distinct from proving original-PDF formatting or source-code execution.
The added syntax gate caught a page-break indentation problem missed by the
original keyword checks. It also exposed one syntax error genuinely present in
the original PDF. Before the final rerun, the supplemental rule was made
source-aware: five examples must compile without execution; the one visually
confirmed source error must match a pre-recorded code hash and emit its warning.
The preliminary all-examples-compile rule and its source-based correction are
retained privately. Neither changes the frozen 25-question content criteria.

Observed presentation limits remain: some answers quote running footers, clipped
stored context, or a repeated source row. The stored model-comparison header also merges
MMLU/Parameters labels across neighboring cells. One original figure description has an
inconsistent branch count even though the diagram is correct. Arabic responses
can retain English source tables/captions. The content checks and scoped manual
review do not certify publication-quality prose, exhaustive translation, or
independent truth of every assertion in the source books. The function
reproduction and syntax qualification here cover Python examples; other source
languages are not qualified by this test set.

No canonical documents were modified or re-ingested, no schema migration was
applied, and no changes were pushed or deployed to a hosted service.
