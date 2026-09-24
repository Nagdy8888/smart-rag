# P7 - Rebuild the image, re-run the 50 known-answer questions, write evidence

## Goal

Prove P0-P6 end to end: rebuild the Compose `api` image from the branch,
run all 50 known-answer questions (each written from a specific page of
the ingested PDF, so the expected answer is known) against that image,
write the evidence document, and compare against the acceptance table in
the index plan. This packet changes no product code. If a metric misses
its target, this packet reports it; it does not tune constants.

## Preconditions

- P0-P5 committed on `fix/ka50-accuracy-repair`, P6 adjudicated, and the
  latest `PR fast` run on the branch is green (`gh pr checks`).
- Full fast tier green locally: `uv run python scripts/check.py --tier fast`
  exits 0.
- Compose stack up with `.env.compose` (`docker compose --env-file
  .env.compose -f docker-compose.yml -f docker-compose.packet8.yml ps`
  shows `api`, `paradedb`, `valkey-*`, `crawl-proxy` healthy).
- `SMART_RAG_EVAL_BASE_URL` in `.private-eval/eval-credentials.json` is
  the laptop API (`http://127.0.0.1:8000`).
- The gold document set is unchanged (4 documents; confirm with
  `SELECT count(*) FROM app.documents WHERE deleted_at IS NULL`).

## Steps

0. **Rebuild the image the eval will hit.** Run the three commands under
   "Docker rebuild before any live run" in `00-rules-and-commands.md`.
   Required output: the probe prints `present` for **P0 through P5**
   (six lines, no `MISSING`), and `health/ready` shows
   `"query_ready": true`. Record the image id:
   `docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml images api`
   and the branch commit: `git rev-parse --short HEAD`. Both go into the
   evidence doc. If any probe line says `MISSING`, stop: the image is
   stale or a packet is not on the branch; a run now is not evidence.
1. Archive the previous run: move `ka50-answers.json`,
   `ka50-progress.json`, `ka50-stages.json`, `ka50-summary.json` from
   `.private-eval/` into `.private-eval/runs/2026-09-22-baseline/`. If
   `ka50-answers.json` stays in place the runner resumes and skips
   questions; the run must start from zero.
2. Run the full 50-question command from `00-rules-and-commands.md`
   (about 50 minutes). Keep the terminal output; the DIAG lines and
   `drop_histogram=` are the primary evidence. Confirm the summary says
   `questions: 50`.
3. Compute the stage table with the private helper
   `uv run python .private-eval/page_in_pool.py` (it reads
   `ka50-stages.json`; extend it to also count `rerank_pool_ids` hits
   using the same chunk->page map - private file, no docstring rules
   beyond keeping it readable).
4. Fill the acceptance table (below).
5. For every remaining miss, list: id, new drop bucket, gold fused rank
   and pool membership, terminal, detail. Group by bucket. Name the
   packet that should own each residual (or "reranker ranked gold below
   cut - out of scope").
6. Write `docs/evaluation/KNOWN_ANSWER_50_REPAIR_EVIDENCE_<date>.md`:
   branch commit and `api` image id from step 0, commands with exit
   codes, the acceptance table, the residual list, per-question wall time
   before/after P5, deviations, and a `flowchart` Mermaid of the new
   drop-bucket decision. No answer text, no gold phrases, no DSNs. Link it
   from `KNOWN_ANSWER_50_REVIEW_2026-09-22.md`,
   `KNOWN_ANSWER_50_ROOT_CAUSES_2026-09-22.md`, and add it to
   `docs/README.md` with owner/status/last-reviewed.
7. Update the index plan todos: mark P0-P7 `completed` only for packets
   whose Done-when lists are fully proven. Leave partial ones
   `in_progress` with a one-line reason.
8. If `strict_pass < 32`: do not tune anything here. Write the residual
   list, commit the evidence (below), and report which packet owns the
   biggest residual bucket. The user decides whether to reopen that
   packet on the same branch before P8.

## Acceptance table

| Metric | Baseline | This run | Target | Pass |
| --- | ---: | ---: | ---: | --- |
| `strict_pass` | 17 | | >= 32 | |
| `grounded_fact_pass` | 17 | | >= 36 | |
| gold in `rerank_pool_ids` | 31 | | >= 46 | |
| gold in `selected_ids` | 31 | | >= 42 | |
| `retrieval_profile_id == hybrid_long_document_v2` | 0 | | 50 | |
| `deadline` bucket with all phrases present | 2-4 | | 0 | |
| `citation_persist_failed` terminals | 3 | | 0 | |
| `drop_histogram` | `citation:2,deadline:4,pass:17,phrasing:5,retrieval_miss:18,verifier_refusal:4` | | | |

## Done when

- [ ] `api` image rebuilt from the branch head; probe printed `present`
      for P0-P5; image id and commit recorded.
- [ ] Fresh 50-question run (`questions: 50`, started from an empty
      `--answers-out`) completed with stage export and verbose DIAG lines.
- [ ] Acceptance table filled with measured numbers.
- [ ] Every residual miss named with its bucket and owning packet.
- [ ] Evidence doc written, linked, indexed; `scripts/check.py --tier docs`
      passes.
- [ ] Index plan todo statuses updated truthfully.
- [ ] Committed and pushed; `gh pr checks --watch --fail-fast` exit 0.

## Commit

Follow "At the end of every packet" in `00-rules-and-commands.md`. Files:
the new evidence doc, the two review docs it links from, `docs/README.md`,
and `.cursor/plans/ka50_accuracy_repair_7e21c4d9.plan.md` (todo statuses).
Message:

```text
docs(eval): KA50 repair evidence - <strict_pass>/50 strict on rebuilt image (P7)
```

Replace `<strict_pass>` with the measured number; never round it up.

## Do not

- Do not edit constants, profiles, prompts, or gold between the run and
  the write-up.
- Do not re-run single questions to improve numbers; one run is the
  evidence. A second full run is allowed only to check variance, and both
  are then reported.
