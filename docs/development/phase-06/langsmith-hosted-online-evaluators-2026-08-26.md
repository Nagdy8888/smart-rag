# LangSmith hosted online evaluators (2026-08-26)

Parent index: [phase-06-agent-intelligence-evidence.md](../phase-06-agent-intelligence-evidence.md).

Narrow follow-up on Packet 7 evaluation. Does not advance general-chat
packets or mark Phase 6 complete.

## Acceptance checks restated

- Two workspace evaluators exist and attach only to
  `smart-rag-agent-eval-online`.
- One evaluator is deterministic code
  (`smart-rag-agent-online-hard-metrics-v1`); one is a hosted
  `gpt-4o-mini` structured judge (`smart-rag-agent-online-judge-v1`)
  using pinned `eval_judge_v1` / `smart-rag-eval-judge-v1`.
- At most 20 synthetic development traces per invocation from
  `tests/fixtures/evaluation/phase6/online_agent_eval_v1.json`.
- Holdout stays denied. Real-company content is never exported. The
  normal `smart-rag` project remains untouched.
- Online rules use `sampling_rate=1.0`, filter
  `eq(name, "query.agent.eval.online.v1")`, no backfill, weekly USD 2
  spend cap on the LLM rule.
- Hosted feedback is the success criterion. Evaluator creation alone
  is not success.

## Local proof

| Command | Exit | Notes |
| --- | --- | --- |
| `uv run python -m pytest tests/unit/test_agent_eval.py tests/unit/test_langsmith_agent_runner.py tests/unit/test_query_agent_eval_trace.py tests/unit/test_langsmith_online_evaluator.py -q` | 0 | 36 passed. Suite, envelope, scorer parity, fail-closed, CLI contract |
| `uv run ruff format --check` on the changed Python set | 0 | After format of provision, hosted evaluator, and verify scripts |
| `uv run ruff check` on the changed Python set | 0 | All checks passed |
| `uv run python -m pyright` on the changed Python set | 0 | Strict, 0 errors |
| `uv run python scripts/eval_query_agent_langsmith.py --online-only --dry-run` | 0 | Frozen 20-id suite, project `smart-rag-agent-eval-online`, `holdout_opened=false`, `writes=false` |
| `uv run python scripts/langsmith/setup_online_agent_evaluators.py --dry-run --model-configuration-id 00000000-0000-0000-0000-000000000000` | 0 | Local contract only; `writes=false` |

Dry-run identity: suite hash
`d8f5daa0e05a75d8bcd30fc2356ad4d9b8d83555a7ca0ae5ac15032d9edbf8d5`,
manifest hash
`35358ee378445d8318d09074d578866c7b44f97c97af33f14ed09b6d0ddb7301`,
root `query.agent.eval.online.v1`, schema `agent-online-eval-v1`,
sampling `1.0`, weekly spend `2.00`, concurrency 1, repetitions 1,
no dataset/experiment, no local judge.

## Live workspace proof

Authenticated 2026-08-26 against the existing local LangSmith key
(never printed). Official Windows CLI `langsmith` **0.2.51**. Two
consecutive setup runs printed the same IDs. Open **Tracing →
`smart-rag-agent-eval-online` → Evaluators**, not `smart-rag-demo-3`.

| Item | Value |
| --- | --- |
| Dedicated project | `smart-rag-agent-eval-online` |
| Dedicated project id | `0be241df-90e1-4f96-bfa0-2be48b38ac9b` |
| Application project in this workspace | `smart-rag-demo-3` id `74ffccd3-c739-42e9-8a12-4a052c663d82` (no evaluator rules) |
| Named `smart-rag` project | **absent** from the workspace listing |
| Code evaluator | `smart-rag-agent-online-hard-metrics-v1` id `f726fe1c-14e8-40ee-bb4f-1be6d2f3e73b` |
| LLM evaluator | `smart-rag-agent-online-judge-v1` id `eae1c165-f195-4dd4-abbb-5fa9d65d7b16` |
| Code rule | `smart-rag-agent-online-hard-metrics-v1-rule` id `615e3385-a3a8-41f3-89b6-ef008be64587` |
| LLM rule | `smart-rag-agent-online-judge-v1-rule` id `4e579da2-0155-46c0-bfa1-99b06b9aafe0` |
| Prompt commit / tag | `agent-online-eval-v1` |
| Local prompt SHA-256 | `4901762bfa4a7207690384c52d57a3cde3a06ad647b1cf21fc574b8738fc9ae8` |
| Model | `gpt-4o-mini` |
| Model configuration | `smart-rag-eval-gpt-4o-mini` id `279906e1-2c03-4080-8511-aa194c663073` (references existing workspace secret name `OPENAI_API_KEY`; no key uploaded) |
| Filter | `eq(name, "query.agent.eval.online.v1")` |
| Sampling | `1.0` |
| Spend cap | requested USD 2.00 weekly; **not enforced** (`Spend limits are not available for your organization`) |
| Emitted root traces | **0**. Live `--online-only` not yet run |
| Feedback complete on every root | **unverified** until a bounded batch is emitted |
| Application-project evaluator rules | `runs/rules?session_id=74ffccd3-…` is `[]` |

## Rollback

No dedicated project, evaluator, or rule was created, so there is
nothing to roll back. If a later operator run creates the two rules:

1. Disable or delete only the two dedicated-project rules.
2. Delete the two evaluator resources if no other rule references them.
3. Do not delete `smart-rag` / `smart-rag-demo-3` traces, those
   application projects, or shared prompts without an explicit
   reference check.

## Stop conditions that remain live

**Stopped** without improvising: no existing LangSmith `gpt-4o-mini`
playground / model configuration is available. Setup was not run with
a fabricated UUID. No OpenAI key was uploaded and no provider
integration or playground setting was created. Traces were not emitted
to manufacture feedback.

Resume only after an operator saves an existing workspace
`gpt-4o-mini` model configuration (LangSmith **Settings → Model
configurations** / Playground save), then:

```powershell
.\scripts\langsmith\setup_online_agent_evaluators.ps1 -ModelConfigurationId <existing-gpt-4o-mini-id>
.\scripts\langsmith\setup_online_agent_evaluators.ps1 -ModelConfigurationId <existing-gpt-4o-mini-id>
uv run python scripts/eval_query_agent_langsmith.py --online-only --allow-bm25-degraded
uv run python scripts/langsmith/verify_online_agent_feedback.py --expected-roots 20 --timeout-seconds 600
```

The second setup run must reprint the same evaluator and rule IDs.
Success still requires feedback on every eligible root, not evaluator
creation alone.
