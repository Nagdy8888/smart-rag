# Live user-flow follow-up

Date: 20 October 2026. This follow-up replaces neither the original review nor
the fixed synthetic regression. The user clarified that questions must be sent
as real app messages, with actual agent processing visible in the terminal.

## What ran

- Started Docker Desktop, rebuilt the API image with the local agent fixes, and
  started the frontend. Mock model mode was false.
- Recovered the empty local derived BM25 index from three current canonical
  document versions. All three passed the existing projection parity verifier.
  Canonical access was read-only; no document/job finalization was performed.
- Signed in with the existing private evaluator credentials, created a fresh
  conversation per question, submitted to the same authenticated message endpoint
  as the app, and consumed actual SSE responses from live retrieval/providers.
- Ran 25 document questions: eight prose, six code, six table, and five figure
  questions. Four use Arabic. These are fresh wordings of known development
  topics, not an unseen holdout. They are a different set from the synthetic
  release-integrity fixtures.
- Printed each question, stage progress, actual returned answer, final status,
  elapsed time, conversation ID, and run ID. No browser-click journey is claimed.

## Observed outcomes

All **25 valid questions** received terminal results: **13 completed, 12 partial**.
Six returned the new verification-unavailable refusal. These are execution
outcomes, not 13 correctness passes or a measured accuracy percentage.

Checkpoint verification states were 13 `verified`, six `verified_partial`, and
six `refused`. The refusals comprised four `verifier_verdict_mismatch` and two
`TimeoutAfterSendError` outcomes. The latter conservatively represents an
uncertain gateway outcome; it is not proof of a provider-side timeout.

All 25 assistant messages were persisted, and their text matched the streamed
text after HTML unescaping and whitespace trimming. All six refused answers
persisted zero citations. Durable usage for the final valid set contained 25
entries each for answer, embedding, rerank, and verifier, with no organizer entry.
These checks establish text parity/accounting observations, not citation
correctness or answer accuracy.

Observed problems include verifier verdict-ID mismatches, unresolved citations,
incomplete requested code, unrelated extra tables/figures, and English responses
to Arabic questions. These require stage-specific follow-up. A completed terminal
alone does not establish completeness, relevance, language matching, exact code,
or correct-page citation quality.

The first run also contained four malformed Arabic inputs caused by PowerShell
stdin encoding in the temporary dataset-generation command. Those attempts were
archived separately and all four prompts were resubmitted with correct UTF-8.
The final 25-question results exclude the four invalid-input attempts; there were
29 submissions in total. Their costs and conversations still exist.

## Private evidence

Unrestricted questions and answers remain gitignored under `.private-eval/`:

- `agent-live-user-flow-25-2026-10-20-v1.json`: corrected question set.
- `agent-live-user-flow-25-2026-10-20-terminal.txt`: terminal transcript, including
  the original and explicitly identified corrected-input run.
- `agent-live-user-flow-25-2026-10-20-results.json`: final 25 valid results.
- `agent-live-user-flow-25-2026-10-20-initial-attempts.json`: preserved first batch.
- `agent-live-user-flow-25-2026-10-20-invalid-encoding-attempts.json`: four excluded
  malformed-input results.
- `live-bm25-recovery-2026-10-20.json`: local index parity checks.
- `agent-live-user-flow-25-2026-10-20-summary.json`: persisted text parity,
  verifier outcomes, durable usage counts, dataset hash, and checked image ID.
- `agent-live-user-flow-25-2026-10-20-stages.json`: private retrieval diagnostics.
- `run_agent_live_user_flow_25.py`: private runner; resumes saved question IDs.

This run establishes real authenticated message execution and preserves visible
results. It does not supply a baseline-versus-patch quality comparison, gold
adjudication, complete release qualification, or browser interaction coverage.
The safety changes remain in place; refusal rates are not reduced by restoring
unchecked drafts or weakening verifier-ID checks.
