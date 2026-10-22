# Agent failure repair — 22 October 2026

## Scope and evidence

The local mixed-50 baseline remains unchanged. Its strict audit and manual
spot review flagged 13 cases. Diagnosis used the saved answers, local LangGraph
checkpoints, canonical source chunks, and original PDF text, rather than only
the terminal verifier node.

Private evidence is under `.private-eval/local-mixed50-20261022/` and the separate
candidate run folders. These development questions are not an independent holdout.

## Implemented changes

- Preserve original source offsets when Unicode case folding expands characters.
  Reject excerpts whose required context cannot fit without cutting a sentence.
- Require explicitly named entities/years to exist in fitted evidence before
  generic keyword-based excerpt salvage can replace a refusal.
- Carry canonical parent IDs through Hybrid fusion. Adjacent native code
  fragments with the same document, version, section, and parent can be joined
  only when the bounded result parses as one function. Both exact fragments
  remain separately cited. Ambiguous continuations fail closed.
- Preserve the explanation and citation ownership when formatting an answer
  containing both code and prose. Do not silently truncate an oversized block.
- Recover a proven named source function after a provider failure without a
  second model call.
- Replace heading-only citation spans with exact following body text from the
  same canonical record before ordinary grounding and leaf persistence.
- Keep explanatory/translated answers when a table is only their evidence;
  prevent generic English excerpt fallback from replacing Arabic prose.
- Pin `answer_v13` with explicit translated descriptive table cells and
  multipart presentation requirements. Numbers, names, predicates and quoted
  source spans remain faithful.
- Preserve explicitly ordered `first ...; then ...` questions as two bounded
  retrieval inputs, retaining the original question for answering and the
  same authorization/reservation context for every branch.

## Verification and limitations

The scoped Python regression group passed 325 tests with one skipped, followed
by 37 passing targeted code-formatting and explanation tests. Changed runtime modules
passed strict type checks. The first targeted app rerun is retained separately;
it is not a full-suite acceptance result.

The second candidate completed the unchanged 50-question authenticated
conversation/SSE regression: 42/50 basic checks and 39/50 strict checks passed.
Later targeted runs are diagnostic only: a four-case basic pass still missed
substantive code explanations on manual inspection. After additional repairs,
a ten-case code/reading run passed nine basic checks; one code/explanation
request still refused, and another retained only introductory prose. This is
not 50/50 acceptance. Arabic refusals and the deterministic table calculation
remain unresolved.

Two distinct source/feature issues need explicit treatment: the supervisor
example contains a malformed string in the original PDF text, and the numeric
comparison case lacks an executed deterministic table calculation. Reproducing
malformed original code cannot simultaneously satisfy an unchanged exact-copy
request and a Python-syntax acceptance check. Calculation must use authorized
typed table values, never a model-invented result from prose. Neither issue is
hidden by changing the frozen questions or weakening their checks.

Hosted Supabase, its backups, and the frozen baseline data were not deleted or
modified by this repair work. Current verification is local, not a hosted
deployment or production release certification.
