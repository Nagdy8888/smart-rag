# Insufficient evidence diagnosis — 22 October 2026

## What the recorded full run actually showed

The preceding 50-question local run had 39 completed and 11 partial terminal
events. Seven used the `insufficient_evidence` limitation. Two were expected
negative tests about facts absent from the PDF. Five were supported development
questions affected by answer processing: Arabic memory, an Arabic storage table,
an Arabic figure explanation, a code-plus-explanation request, and a multipart
tool/storage question. The full strict acceptance result remained 39/50.

The generic message is not proof of an ACL denial. Saved checkpoints for the
Arabic and code refusals contained 10–11 authorized retrieved passages. Other
cases had provider deadlines or empty retrieval branches. These are distinct
failure stages and must not be fixed by bypassing access checks.

## Confirmed defects and candidate repairs

- Token-based citation retargeting could replace a complete code definition's
  exact source fragments with a prose call site mentioning an incidental method
  name. Complete definitions now retain their established source ownership.
- A repeated PDF chapter heading could remain the citation span after the
  heading-to-body repair. Repeated standalone labels are now skipped so the
  exact following body can be cited.
- A fitted canonical parent can hold a function continuation even when its second
  native child is absent from the fitted context. Reconstruction now accepts that
  parent only with matching document/version, explicit parent identity, a unique
  signature, a recognized page footer, bounded body, and one valid parsed
  function. Source statements remain unchanged and both spans are cited.
- Provider verifier reason codes were discarded after link removal. Checkpoints
  now preserve at most six link verdicts, with an allowlist of short reason codes;
  unexpected free text becomes `unspecified`. This does not change support votes.
- Pinned candidate prompts `answer_v14` and `verifier_v6` clarify substantive
  claims, code explanations, faithful translation, and presentation syntax.
  Exact quotes, identifiers, numbers, negation and tradeoff direction remain
  subject to the existing grounding rules.

## Verification boundaries

An initial seven-case rerun passed three basic checks. After the first repairs,
five passed; another six-case language rerun passed five. The remaining Arabic
table refusal recorded `literal_mismatch` despite having a retrieved source
table and matching product identifiers. Passing a basic check does not certify
complete explanations or fully Arabic output: manual inspection still found
missing code explanation and partial Arabic figure output.

The focused Python group passed 158 tests, including citation preservation,
canonical-parent continuity, duplicate headings, verifier accounting, safe
reason-code persistence, and existing negative grounding cases. Ruff and strict
targeted Pyright passed. A fresh unchanged 50-question app/SSE regression is
started in `.private-eval/local-mixed50-evidence-repair-20261022/`, but was
interrupted after seven saved results. That folder is partial evidence, not a
completed 50-question gate.
Do not claim final acceptance from targeted wins or overwrite the older results.

All changes and checks are local; hosted Supabase, its backup, and the frozen
question dataset were preserved. No authorization filter or refusal threshold
was relaxed.
