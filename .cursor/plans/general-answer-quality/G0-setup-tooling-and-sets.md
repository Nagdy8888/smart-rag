# G0 - Branch, measurement tools, new dev/holdout sets, and baselines

Read [`00-rules-and-commands.md`](./00-rules-and-commands.md) first.

**Depends on:** nothing. **Live run:** yes (dev40 and holdout40 baselines,
about 40 to 80 minutes total). **Runtime code changes:** none. This packet
adds tools, docs, private sets, and baselines only.

## Goal

1. Park the uncommitted fresh-30 work so it cannot leak into this branch.
2. Add a tracked stage-loss report (`scripts/eval_stage_loss.py`) that
   splits generation losses into "draft never had it" (5a) and "removed
   after the draft" (5b), with the removal cause.
3. Add a tracked guard (`scripts/check_gold_literals.py`) that fails when
   gold phrases are baked into application code.
4. Add the Cursor rule, runbook, ADR, and evidence doc.
5. Write two new private 40-question sets (dev40 and sealed holdout40).
6. Rebuild the `api` image from clean `main` and record both baselines.

## Read first (confirm each exists)

- `scripts/run_company_ask.py`: `parser.add_argument("--gold", type=Path, required=True)`
  and the merge loop `for question_id, row in answers.items():` that writes
  `row["stages"] = stages` (around line 800-815).
- `scripts/eval_ask_stage_export.py`: `REQUIRED_FIELDS` includes
  `"dense_ids"`, `"bm25_ids"`, `"term_ids"`, `"fused_ids"`,
  `"selected_ids"`, `"rerank_pool_ids"`.
- `packages/core/src/smart_rag_core/evaluation/company_ask_regression.py`:
  `def load_private_gold(path: Path) -> tuple[CompanyAskQuestion, ...]:`
  and `class CompanyAskQuestion` with `question_id`, `prompt`, `facts`,
  `page`, `kind`.
- `packages/core/src/smart_rag_core/evaluation/dual_metric.py`:
  `class RequiredFact` with `fact_id`, `canonical_phrases`,
  `approved_aliases`; `def normalize_answer_text(answer_text: str) -> str:`;
  `def phrase_is_present(answer_text: str, phrase: str) -> bool:`.
- `packages/core/src/smart_rag_core/query_answer/claims.py`:
  `CLAIM_LINK_PREFIX = "claim-"`.
- `.private-eval/answer50_checkpoint_dump.py` lines 81-98: the
  `langgraph.checkpoint_writes` query and `node = task_path.split(",")[-1].strip()`.
- `.private-eval/extract_fresh30_mixed_dumps.py` (the dump script G0 adapts).
- `tests/unit/test_eval_citation_page_score.py` line 7
  (`from scripts.eval_citation_page_score import score_rows`), which shows
  that tests import scripts as a package.
- `docs/README.md` row format (example line 207):
  `| [evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md](./evaluation/ANSWER_LOSS_REPAIR_EVIDENCE_2026-09.md) | engineering-lead | draft | 2026-09-25 | eng, reviewers |`.
- `docs/adr/README.md` table columns `| ADR | Status | Phase | Path |`.

## Step 1 - Park the fresh-30 work and create the branch

```powershell
git branch --show-current
git status --short
```

Expected: branch `main`; modified `docs/README.md`,
`packages/core/src/smart_rag_core/query_answer/generate_grounded.py`,
`packages/core/src/smart_rag_core/retrieval/rerank.py`,
`tests/unit/test_code_table_literal_salvage.py`,
`tests/unit/test_query_literal_extractive_salvage.py`; untracked
`docs/evaluation/FRESH_KNOWN_ANSWER_30_2026-10-06.md`, `.cursor/hooks.json`,
`.cursor/plans/general-answer-quality/`, and `.private-eval/...`. If other
tracked files are modified, stop and ask the user.

```powershell
git checkout -b wip/fresh30-postfix
git add docs/README.md packages/core/src/smart_rag_core/query_answer/generate_grounded.py packages/core/src/smart_rag_core/retrieval/rerank.py
git add tests/unit/test_code_table_literal_salvage.py tests/unit/test_query_literal_extractive_salvage.py docs/evaluation/FRESH_KNOWN_ANSWER_30_2026-10-06.md
git commit -m "wip: fresh-30 question-specific fixes (parked; never merge)"
git checkout main
git pull --ff-only origin main
git checkout -b fix/general-answer-quality
git status --short
```

Do **not** push `wip/fresh30-postfix`. After the last command, `git status`
must show no modified tracked files (only untracked noise and the plan
folder).

Copy the plan index into the repo and commit the plan:

```powershell
Copy-Item "C:\Users\Nagdy\.cursor\plans\general_answer-quality_repair_ce1b8baf.plan.md" .cursor/plans/general_answer_quality.plan.md
git add .cursor/plans/general_answer_quality.plan.md .cursor/plans/general-answer-quality
git commit -m "docs(plan): general answer-quality repair plan G0-G5"
git push -u origin fix/general-answer-quality
gh pr create --draft --base main --head fix/general-answer-quality --title "fix: general answer-quality repair (G0-G5)" --body "Implements .cursor/plans/general_answer_quality.plan.md. Removes question-specific salvage/promotion code, adds a verbatim-support verifier override, optional locate-quote call, code-layout PDF reflow, and a sealed dev/holdout measurement loop. One commit per packet. gpt-4o-mini only."
```

## Step 2 - `scripts/eval_stage_loss.py` (exact code)

Create the file with exactly this content:

```python
"""Attribute every gold fact in one company-ask run to the stage that lost it.

Operator diagnostic for the answer-quality repair loop
(``docs/runbooks/answer-quality-repair-loop.md``). Inputs are private: a run
folder written by ``scripts/run_company_ask.py`` (``answers.json`` and
optionally ``stages.json``) and the gold file that run used. The script reads
canonical chunk text and LangGraph checkpoint writes through the operator
database URL. Output is counts and question ids only; gold phrases, answer
text, and chunk text are never printed or written.

Stages (the first stage that misses the fact wins):

- ``ok``: the released answer holds the fact (same rule as the scorer).
- ``1_ingestion``: no stored chunk of the run's document versions holds it.
- ``2_retrieval``: no dense, BM25, term, fused, pool, or selected chunk holds it.
- ``3_fusion_pool``: a candidate holds it; the rerank pool does not.
- ``4_rerank_select``: the pool holds it; selected evidence does not.
- ``5a_draft_missing``: selected evidence holds it; the generated draft does not.
- ``5b_removed_after_draft``: the draft held it; the released answer does not.
- ``5_unknown_no_checkpoint``: selected evidence holds it, no draft was found.

Example:
    ``uv run python scripts/eval_stage_loss.py --run .private-eval/runs/dev40-g0
    --gold .private-eval/dev40-2026-10-v1.json``
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    CompanyAskQuestion,
    load_private_gold,
)
from smart_rag_core.evaluation.dual_metric import (  # noqa: E402
    normalize_answer_text,
    phrase_is_present,
)

STAGES: tuple[str, ...] = (
    "ok",
    "1_ingestion",
    "2_retrieval",
    "3_fusion_pool",
    "4_rerank_select",
    "5a_draft_missing",
    "5b_removed_after_draft",
    "5_unknown_no_checkpoint",
)
CANDIDATE_KEYS: tuple[str, ...] = ("dense_ids", "bm25_ids", "term_ids", "fused_ids")
POOL_KEYS: tuple[str, ...] = ("rerank_pool_ids",)
SELECTED_KEYS: tuple[str, ...] = ("selected_ids",)
REMOVAL_CAUSES: tuple[str, ...] = (
    "salvage_overwrite",
    "refused_after_draft",
    "trimmed_or_rewritten",
)
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_CHECKPOINT_SQL = (
    "SELECT task_path, type, blob FROM langgraph.checkpoint_writes"
    " WHERE thread_id = %s AND channel = 'answer' ORDER BY checkpoint_id, idx"
)


@dataclass(frozen=True, slots=True)
class StageIds:
    """Chunk ids one question reached at each retrieval stage.

    Each later stage is folded into the earlier ones, so a selected chunk
    always counts as a candidate and a pool member.

    Attributes:
        candidates: Dense, BM25, term, fused, pool, and selected ids.
        pool: Rerank pool ids (fused ids when the pool is empty) plus selected.
        selected: Evidence ids handed to the answer model.
    """

    candidates: frozenset[str]
    pool: frozenset[str]
    selected: frozenset[str]


@dataclass(frozen=True, slots=True)
class DraftView:
    """Generated draft and released payload facts for one question.

    Attributes:
        draft_text: Draft ``answer_text`` plus every draft claim, newline-joined.
        draft_link_ids: Draft atomic link ids.
        final_link_ids: Released atomic link ids.
        final_status: Released payload ``status``.
    """

    draft_text: str = ""
    draft_link_ids: tuple[str, ...] = ()
    final_link_ids: tuple[str, ...] = ()
    final_status: str = ""


def collapse(text: str) -> str:
    """Normalize like the scorer, then collapse whitespace.

    Chunk text wraps lines where gold phrases do not, so containment checks
    against stored chunks collapse whitespace on both sides.

    Args:
        text: Any text.

    Returns:
        Scorer-normalized text with single spaces.
    """

    return " ".join(normalize_answer_text(text).split())


def uuid_ids(stage: Mapping[str, object], keys: Iterable[str]) -> frozenset[str]:
    """Collect UUID-shaped ids from list-valued stage fields.

    Stage exports write the string ``"unknown"`` when a field is missing, so
    non-list values and non-UUID items are ignored.

    Args:
        stage: One question's ``stages`` mapping.
        keys: Field names to read.

    Returns:
        Lowercased UUID strings.
    """

    found: set[str] = set()
    for key in keys:
        value = stage.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            text = str(item).strip().lower()
            if _UUID.match(text):
                found.add(text)
    return frozenset(found)


def stage_ids(stage: Mapping[str, object]) -> StageIds:
    """Build monotonic stage id sets for one question.

    Args:
        stage: One question's ``stages`` mapping.

    Returns:
        Candidate, pool, and selected id sets.
    """

    selected = uuid_ids(stage, SELECTED_KEYS)
    pool = uuid_ids(stage, POOL_KEYS) or uuid_ids(stage, ("fused_ids",))
    pool = pool | selected
    candidates = uuid_ids(stage, CANDIDATE_KEYS) | pool
    return StageIds(candidates=candidates, pool=pool, selected=selected)


def link_prefix(link_id: str) -> str:
    """Return a link id without its trailing ``-<number>``.

    Args:
        link_id: Atomic link id such as ``claim-2``.

    Returns:
        ``claim`` for ``claim-2``; the input when there is no numeric suffix.
    """

    head, sep, tail = link_id.rpartition("-")
    return head if sep and tail.isdigit() else link_id


def removal_cause(view: DraftView) -> str:
    """Name why a fact present in the draft is missing from the release.

    Args:
        view: Draft and released payload facts.

    Returns:
        ``salvage_overwrite`` when the release holds link families the draft
        did not, ``refused_after_draft`` when the release has no links or is
        refused, else ``trimmed_or_rewritten``.
    """

    draft = {link_prefix(item) for item in view.draft_link_ids}
    final = {link_prefix(item) for item in view.final_link_ids}
    if final - draft:
        return "salvage_overwrite"
    if view.final_status == "refused" or not view.final_link_ids:
        return "refused_after_draft"
    return "trimmed_or_rewritten"


def _links(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """Return the dict-shaped atomic links of a decoded payload.

    Args:
        payload: Decoded ``answer`` channel value, or None.

    Returns:
        Atomic link mappings; empty when absent.
    """

    raw = payload.get("atomic_links") if payload else None
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, dict)]


def view_from_payloads(
    draft: Mapping[str, Any] | None, final: Mapping[str, Any] | None
) -> DraftView | None:
    """Build a draft view from decoded generate and verify payloads.

    Args:
        draft: ``answer`` written by ``generate_answer``, or None.
        final: ``answer`` written by ``verify_answer``, or None.

    Returns:
        The view, or None when no draft was written.
    """

    if draft is None:
        return None
    draft_links = _links(draft)
    final_links = _links(final)
    claims = [str(item.get("claim") or "") for item in draft_links]
    return DraftView(
        draft_text="\n".join([str(draft.get("answer_text") or ""), *claims]),
        draft_link_ids=tuple(str(item.get("link_id") or "") for item in draft_links),
        final_link_ids=tuple(str(item.get("link_id") or "") for item in final_links),
        final_status=str((final or {}).get("status") or ""),
    )


def classify_fact(
    phrases: Sequence[str],
    *,
    answer_text: str,
    view: DraftView | None,
    ids: StageIds,
    text_by_id: Mapping[str, str],
    corpus_ids: frozenset[str],
) -> str:
    """Return the first stage that lost one fact.

    Args:
        phrases: Canonical phrases plus approved aliases of the fact.
        answer_text: Released answer text from ``answers.json``.
        view: Draft view, or None when no checkpoint was found.
        ids: Stage id sets for the question.
        text_by_id: Chunk id to ``collapse``-normalized chunk text.
        corpus_ids: Every chunk id of the run's document versions.

    Returns:
        One value of ``STAGES``.
    """

    if any(phrase_is_present(answer_text, phrase) for phrase in phrases):
        return "ok"
    keys = [key for key in (collapse(phrase) for phrase in phrases) if key]

    def holds(chunk_ids: Iterable[str]) -> bool:
        """Return whether any listed chunk contains any phrase key.

        Args:
            chunk_ids: Chunk ids to check.

        Returns:
            True on the first containing chunk.
        """

        return any(key in text_by_id.get(chunk_id, "") for chunk_id in chunk_ids for key in keys)

    if not holds(corpus_ids):
        return "1_ingestion"
    if not holds(ids.candidates):
        return "2_retrieval"
    if not holds(ids.pool):
        return "3_fusion_pool"
    if not holds(ids.selected):
        return "4_rerank_select"
    if view is None:
        return "5_unknown_no_checkpoint"
    draft_key = collapse(view.draft_text)
    if not any(key in draft_key for key in keys):
        return "5a_draft_missing"
    return "5b_removed_after_draft"


def fact_phrases(question: CompanyAskQuestion) -> list[list[str]]:
    """Return canonical phrases plus aliases for every fact of a question.

    Args:
        question: Loaded gold question.

    Returns:
        One phrase list per fact.
    """

    return [
        [*fact.canonical_phrases, *fact.approved_aliases] for fact in question.facts
    ]


def build_report(
    questions: Sequence[CompanyAskQuestion],
    answers: Mapping[str, Mapping[str, Any]],
    *,
    stages_by_id: Mapping[str, StageIds],
    views: Mapping[str, DraftView | None],
    text_by_id: Mapping[str, str],
    corpus_ids: frozenset[str],
) -> dict[str, Any]:
    """Classify every fact and aggregate counts.

    Args:
        questions: Gold questions in run order.
        answers: Runner ``answers.json`` rows keyed by question id.
        stages_by_id: Stage id sets keyed by question id.
        views: Draft views keyed by question id.
        text_by_id: Chunk id to normalized text.
        corpus_ids: Chunk ids of the run's document versions.

    Returns:
        JSON-ready report with ``questions``, ``facts``, ``strict_passes``,
        ``stages``, ``removed_after_draft_causes``, ``by_kind``, and
        ``question_ids_by_stage``.
    """

    stage_counts: Counter[str] = Counter({stage: 0 for stage in STAGES})
    causes: Counter[str] = Counter({cause: 0 for cause in REMOVAL_CAUSES})
    by_kind: dict[str, Counter[str]] = {}
    ids_by_stage: dict[str, list[str]] = {stage: [] for stage in STAGES}
    strict = 0
    asked = 0
    facts_total = 0
    for question in questions:
        row = answers.get(question.question_id)
        if row is None:
            continue
        asked += 1
        answer_text = str(row.get("answer_text") or "")
        ids = stages_by_id.get(
            question.question_id,
            StageIds(frozenset(), frozenset(), frozenset()),
        )
        view = views.get(question.question_id)
        all_ok = True
        kind_counts = by_kind.setdefault(question.kind or "unknown", Counter())
        for phrases in fact_phrases(question):
            facts_total += 1
            stage = classify_fact(
                phrases,
                answer_text=answer_text,
                view=view,
                ids=ids,
                text_by_id=text_by_id,
                corpus_ids=corpus_ids,
            )
            stage_counts[stage] += 1
            kind_counts[stage] += 1
            if question.question_id not in ids_by_stage[stage]:
                ids_by_stage[stage].append(question.question_id)
            if stage != "ok":
                all_ok = False
            if stage == "5b_removed_after_draft" and view is not None:
                causes[removal_cause(view)] += 1
        strict += int(all_ok)
    return {
        "questions": asked,
        "facts": facts_total,
        "strict_passes": strict,
        "stages": dict(stage_counts),
        "removed_after_draft_causes": dict(causes),
        "by_kind": {kind: dict(counts) for kind, counts in sorted(by_kind.items())},
        "question_ids_by_stage": ids_by_stage,
    }


def load_env() -> dict[str, str]:
    """Read ``KEY=VALUE`` lines from ``.env`` then ``.env.compose``.

    Returns:
        Merged mapping; later files win.
    """

    values: dict[str, str] = {}
    for name in (".env", ".env.compose"):
        path = REPO / name
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_stage_rows(
    run_dir: Path, answers: Mapping[str, Mapping[str, Any]]
) -> dict[str, StageIds]:
    """Read stage ids from ``answers.json`` with a ``stages.json`` fallback.

    Args:
        run_dir: Run folder.
        answers: Runner answers keyed by question id.

    Returns:
        Stage id sets keyed by question id.
    """

    exported: Mapping[str, Any] = {}
    stages_path = run_dir / "stages.json"
    if stages_path.is_file():
        raw = json.loads(stages_path.read_text(encoding="utf-8"))
        runs = raw.get("runs") if isinstance(raw, dict) else None
        exported = runs if isinstance(runs, dict) else {}
    result: dict[str, StageIds] = {}
    for qid, row in answers.items():
        stage = row.get("stages")
        ids = stage_ids(stage if isinstance(stage, dict) else {})
        fallback = exported.get(qid)
        if not ids.selected and isinstance(fallback, dict):
            ids = stage_ids(fallback)
        result[qid] = ids
    return result


def load_database_facts(
    connection: Any,
    stages_by_id: Mapping[str, StageIds],
    answers: Mapping[str, Mapping[str, Any]],
) -> tuple[dict[str, str], frozenset[str], dict[str, DraftView | None]]:
    """Load chunk text, corpus ids, and draft views. Read-only.

    Args:
        connection: Open psycopg connection with ``SET ROLE postgres``.
        stages_by_id: Stage id sets keyed by question id.
        answers: Runner answers keyed by question id.

    Returns:
        Normalized text by chunk id, corpus chunk ids, and draft views.
    """

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    stage_chunk_ids = sorted({cid for ids in stages_by_id.values() for cid in ids.candidates})
    versions = [
        str(row[0])
        for row in connection.execute(
            "SELECT DISTINCT version_id::text FROM app.document_chunks"
            " WHERE id = ANY(%s::uuid[])",
            (stage_chunk_ids,),
        ).fetchall()
    ]
    rows = connection.execute(
        "SELECT id::text, raw_text FROM app.document_chunks"
        " WHERE version_id = ANY(%s::uuid[]) AND deleted_at IS NULL",
        (versions,),
    ).fetchall()
    text_by_id = {str(cid): collapse(str(text or "")) for cid, text in rows}
    corpus_ids = frozenset(text_by_id)
    missing = [cid for cid in stage_chunk_ids if cid not in text_by_id]
    if missing:
        for cid, text in connection.execute(
            "SELECT id::text, raw_text FROM app.document_chunks WHERE id = ANY(%s::uuid[])",
            (missing,),
        ).fetchall():
            text_by_id[str(cid)] = collapse(str(text or ""))
    serde = JsonPlusSerializer()
    views: dict[str, DraftView | None] = {}
    for qid, row in answers.items():
        thread_id = str(row.get("conversation_id") or "")
        draft: Mapping[str, Any] | None = None
        final: Mapping[str, Any] | None = None
        if thread_id:
            for task_path, kind, blob in connection.execute(
                _CHECKPOINT_SQL, (thread_id,)
            ).fetchall():
                if blob is None:
                    continue
                value = serde.loads_typed((kind, bytes(blob)))
                if not isinstance(value, dict):
                    continue
                node = str(task_path).split(",")[-1].strip()
                if node == "generate_answer":
                    draft = value
                elif node == "verify_answer":
                    final = value
        views[qid] = view_from_payloads(draft, final)
    return text_by_id, corpus_ids, views


def _private_path(path: Path) -> Path:
    """Resolve an output path and refuse anything outside ``.private-eval``.

    Args:
        path: Path from the command line.

    Returns:
        Resolved path.

    Raises:
        SystemExit: If the path is outside ``.private-eval``.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise SystemExit(f"refusing to write outside .private-eval: {path}")
    return resolved


def print_report(report: Mapping[str, Any], *, aggregate_only: bool) -> None:
    """Print count lines and, unless aggregate-only, question ids per stage.

    Args:
        report: Output of ``build_report``.
        aggregate_only: True for the sealed holdout (no question ids).
    """

    print(
        f"questions={report['questions']} facts={report['facts']}"
        f" strict_passes={report['strict_passes']}"
    )
    for stage in STAGES:
        print(f"stage {stage} {report['stages'].get(stage, 0)}")
    for cause in REMOVAL_CAUSES:
        print(f"cause {cause} {report['removed_after_draft_causes'].get(cause, 0)}")
    for kind, counts in report["by_kind"].items():
        cells = " ".join(f"{stage}={counts.get(stage, 0)}" for stage in STAGES)
        print(f"kind {kind} {cells}")
    if aggregate_only:
        return
    for stage in STAGES:
        if stage == "ok":
            continue
        ids = report["question_ids_by_stage"].get(stage) or []
        print(f"ids {stage} {','.join(ids) if ids else '-'}")


def main(argv: list[str] | None = None) -> int:
    """Run the stage-loss report for one run folder.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 on success; 2 when inputs are missing.

    Side Effects:
        Read-only database queries; optional ``--json-out`` file under
        ``.private-eval``.
    """

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument("--aggregate-only", action="store_true")
    args = parser.parse_args(argv)
    answers_path = args.run / "answers.json"
    if not answers_path.is_file():
        print(f"blocked=missing {answers_path}", file=sys.stderr)
        return 2
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    questions = load_private_gold(args.gold)
    stages_by_id = load_stage_rows(args.run, answers)
    env = load_env()
    if "OPERATOR_SUPABASE_DB_URL" not in env:
        print("blocked=missing OPERATOR_SUPABASE_DB_URL", file=sys.stderr)
        return 2
    import psycopg

    with psycopg.connect(env["OPERATOR_SUPABASE_DB_URL"], connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        connection.execute("SET TRANSACTION READ ONLY")
        text_by_id, corpus_ids, views = load_database_facts(
            connection, stages_by_id, answers
        )
    report = build_report(
        questions,
        answers,
        stages_by_id=stages_by_id,
        views=views,
        text_by_id=text_by_id,
        corpus_ids=corpus_ids,
    )
    print_report(report, aggregate_only=args.aggregate_only)
    if args.json_out is not None:
        target = _private_path(args.json_out)
        if args.aggregate_only:
            report = {key: value for key, value in report.items() if key != "question_ids_by_stage"}
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

If the checkpoint query fails with `column "idx" does not exist` or
`column "checkpoint_id" does not exist`, delete only the
` ORDER BY checkpoint_id, idx` part of `_CHECKPOINT_SQL` and note it under
**Deviations**.

## Step 3 - `tests/unit/test_eval_stage_loss.py` (exact code)

```python
"""Unit tests for the stage-loss classifier in ``scripts/eval_stage_loss.py``."""

from __future__ import annotations

from scripts.eval_stage_loss import (
    DraftView,
    StageIds,
    classify_fact,
    collapse,
    link_prefix,
    removal_cause,
    stage_ids,
    view_from_payloads,
)

A = "00000000-0000-4000-8000-00000000000a"
B = "00000000-0000-4000-8000-00000000000b"
C = "00000000-0000-4000-8000-00000000000c"
TEXT = {A: collapse("The router\nselects the planner tool."), B: collapse("Other text."), C: collapse("More.")}
CORPUS = frozenset(TEXT)
PHRASE = ["selects the planner tool"]


def _ids(candidates: set[str], pool: set[str], selected: set[str]) -> StageIds:
    """Build monotonic stage ids for a test.

    Args:
        candidates: Candidate ids.
        pool: Pool ids.
        selected: Selected ids.

    Returns:
        Stage ids with later stages folded into earlier ones.
    """

    return StageIds(
        candidates=frozenset(candidates | pool | selected),
        pool=frozenset(pool | selected),
        selected=frozenset(selected),
    )


def _classify(answer: str, ids: StageIds, view: DraftView | None) -> str:
    """Classify the shared phrase.

    Args:
        answer: Released answer text.
        ids: Stage ids.
        view: Draft view or None.

    Returns:
        Stage name.
    """

    return classify_fact(
        PHRASE, answer_text=answer, view=view, ids=ids, text_by_id=TEXT, corpus_ids=CORPUS
    )


def test_ok_uses_scorer_normalization() -> None:
    """HTML entities and case do not hide a released fact."""

    assert _classify("It Selects the planner tool &amp; more.", _ids(set(), set(), set()), None) == "ok"


def test_ingestion_when_no_chunk_holds_fact() -> None:
    """A fact absent from every stored chunk is an ingestion loss."""

    result = classify_fact(
        ["absent phrase here"],
        answer_text="",
        view=None,
        ids=_ids({A}, {A}, {A}),
        text_by_id=TEXT,
        corpus_ids=CORPUS,
    )
    assert result == "1_ingestion"


def test_stage_order() -> None:
    """Each stage is reported only when every earlier stage held the fact."""

    draft_without = DraftView(draft_text="unrelated", draft_link_ids=("claim-1",))
    draft_with = DraftView(draft_text="it selects the planner tool", draft_link_ids=("claim-1",))
    assert _classify("", _ids({B}, set(), set()), None) == "2_retrieval"
    assert _classify("", _ids({A}, {B}, set()), None) == "3_fusion_pool"
    assert _classify("", _ids(set(), {A}, {B}), None) == "4_rerank_select"
    assert _classify("", _ids(set(), set(), {A}), None) == "5_unknown_no_checkpoint"
    assert _classify("", _ids(set(), set(), {A}), draft_without) == "5a_draft_missing"
    assert _classify("", _ids(set(), set(), {A}), draft_with) == "5b_removed_after_draft"


def test_stage_ids_ignore_unknown_strings() -> None:
    """``"unknown"`` fields and non-UUID items are ignored."""

    ids = stage_ids({"dense_ids": "unknown", "fused_ids": [A, "w"], "selected_ids": [B]})
    assert ids.selected == frozenset({B})
    assert ids.pool == frozenset({A, B})
    assert ids.candidates == frozenset({A, B})


def test_link_prefix() -> None:
    """Numeric suffixes are removed; other ids stay."""

    assert link_prefix("claim-2") == "claim"
    assert link_prefix("query-literal-extractive-1") == "query-literal-extractive"
    assert link_prefix("p1") == "p1"


def test_removal_causes() -> None:
    """New link families, refusals, and trims are told apart."""

    assert removal_cause(DraftView("", ("claim-1",), ("salvage-1",), "complete")) == "salvage_overwrite"
    assert removal_cause(DraftView("", ("claim-1",), (), "refused")) == "refused_after_draft"
    assert removal_cause(DraftView("", ("claim-1", "claim-2"), ("claim-2",), "complete")) == "trimmed_or_rewritten"


def test_view_from_payloads() -> None:
    """Draft claims are part of the draft text; a missing draft gives None."""

    assert view_from_payloads(None, {"status": "complete"}) is None
    view = view_from_payloads(
        {"answer_text": "x", "atomic_links": [{"link_id": "claim-1", "claim": "y"}]},
        {"status": "refused", "atomic_links": []},
    )
    assert view is not None
    assert view.draft_text == "x\ny"
    assert view.draft_link_ids == ("claim-1",)
    assert view.final_status == "refused"
```

Run:

```powershell
uv run python -m pytest tests/unit/test_eval_stage_loss.py -q
```

Pass: 7 passed. If ruff reports line length on the test file, run
`uv run python -m ruff format scripts/eval_stage_loss.py tests/unit/test_eval_stage_loss.py`
and rerun.

## Step 4 - `scripts/check_gold_literals.py` (exact code)

```python
"""Fail when private gold phrases are baked into application source or prompts.

General-fix guard for the answer-quality repair loop. It loads every private
gold file ``.private-eval/*v1.json`` (gitignored), normalizes each canonical
phrase and alias of at least ``MIN_PHRASE_CHARS`` characters, and searches
tracked application files. Regex escapes are stripped from source first so a
pattern such as ``alpha\\s+beta`` still matches the phrase ``alpha beta``.

A phrase that occurs in more than ``RARE_FILE_LIMIT`` application files is
ordinary vocabulary and is ignored. An application file fails when it holds
at least ``FAIL_HITS_PER_FILE`` rare phrases and is not in the allowlist.
Files under ``WARN_ROOTS`` (tests, scripts) are reported but never fail.

Output is paths, line numbers, set names, question ids, and counts. Phrases
are never printed. Without private gold files (for example in CI) the check
prints ``skipped`` and exits 0.

Example:
    ``uv run python scripts/check_gold_literals.py``
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.dual_metric import normalize_answer_text  # noqa: E402

APP_ROOTS: tuple[str, ...] = ("packages", "apps/agents", "apps/backend")
WARN_ROOTS: tuple[str, ...] = ("tests", "scripts")
SUFFIXES: tuple[str, ...] = (".py", ".md")
MIN_PHRASE_CHARS = 8
RARE_FILE_LIMIT = 2
FAIL_HITS_PER_FILE = 2
WINDOW_LINES = 3
ALLOWLIST = REPO / "scripts" / "gold_literal_allowlist.txt"
PRIVATE_DIR = REPO / ".private-eval"
_REGEX_ESCAPE = re.compile(r"\\[sSbBnwWd][+*?]?")


@dataclass(frozen=True, slots=True)
class Hit:
    """One rare gold phrase found in one file.

    Attributes:
        path: Repository-relative POSIX path.
        line: 1-based line where the phrase starts (window search).
        set_name: Gold file stem.
        question_id: Gold question id.
    """

    path: str
    line: int
    set_name: str
    question_id: str


def normalize_source(text: str) -> str:
    """Strip regex escapes and normalize like the scorer, collapsing spaces.

    Args:
        text: Source text.

    Returns:
        Normalized text.
    """

    stripped = text.replace("(?i)", " ")
    stripped = _REGEX_ESCAPE.sub(" ", stripped).replace("\\", "")
    return " ".join(normalize_answer_text(stripped).split())


def load_gold_phrases(private_dir: Path) -> dict[str, tuple[str, str]]:
    """Load normalized gold phrases from every private ``*v1.json`` file.

    Args:
        private_dir: The ``.private-eval`` folder.

    Returns:
        Normalized phrase to ``(set_name, question_id)`` (first seen wins).
    """

    phrases: dict[str, tuple[str, str]] = {}
    for path in sorted(private_dir.glob("*v1.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = data if isinstance(data, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            for fact in row.get("facts") or []:
                if not isinstance(fact, dict):
                    continue
                for raw in [*(fact.get("canonical") or []), *(fact.get("aliases") or [])]:
                    key = normalize_source(str(raw))
                    if len(key) >= MIN_PHRASE_CHARS:
                        phrases.setdefault(key, (path.stem, str(row.get("id") or "")))
    return phrases


def tracked_files(roots: Sequence[str], *, exclude_tests: bool) -> list[str]:
    """List tracked ``.py`` and ``.md`` files under roots.

    Args:
        roots: Repository-relative roots.
        exclude_tests: Drop paths with a ``tests`` directory segment
            (application roots); keep them for warning roots.

    Returns:
        POSIX paths.
    """

    output = subprocess.run(
        ["git", "ls-files", *roots], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout
    return [
        path
        for path in output.split()
        if path.endswith(SUFFIXES)
        and not (exclude_tests and "/tests/" in f"/{path}")
    ]


def first_line(raw_text: str, phrase: str) -> int:
    """Return the 1-based line where a phrase starts, by window search.

    Args:
        raw_text: Original file text.
        phrase: Normalized phrase.

    Returns:
        Line number, or 0 when only the whole-file text matches.
    """

    lines = raw_text.splitlines()
    for index in range(len(lines)):
        window = normalize_source(" ".join(lines[index : index + WINDOW_LINES]))
        if phrase in window:
            return index + 1
    return 0


def scan(
    app_texts: Mapping[str, str],
    warn_texts: Mapping[str, str],
    phrases: Mapping[str, tuple[str, str]],
    allowlist: frozenset[str],
) -> tuple[dict[str, list[Hit]], dict[str, list[Hit]]]:
    """Find rare gold phrases in application and warning files.

    Args:
        app_texts: Application path to raw text.
        warn_texts: Test/script path to raw text.
        phrases: Normalized phrase to ``(set_name, question_id)``.
        allowlist: Application paths exempt from failing.

    Returns:
        Failing application hits and warning hits, keyed by path.
    """

    app_norm = {path: normalize_source(text) for path, text in app_texts.items()}
    warn_norm = {path: normalize_source(text) for path, text in warn_texts.items()}
    app_hits: dict[str, list[Hit]] = defaultdict(list)
    warn_hits: dict[str, list[Hit]] = defaultdict(list)
    for phrase, (set_name, qid) in phrases.items():
        holders = [path for path, text in app_norm.items() if phrase in text]
        if len(holders) > RARE_FILE_LIMIT:
            continue
        for path in holders:
            if path in allowlist:
                continue
            app_hits[path].append(Hit(path, first_line(app_texts[path], phrase), set_name, qid))
        for path, text in warn_norm.items():
            if phrase in text:
                warn_hits[path].append(Hit(path, first_line(warn_texts[path], phrase), set_name, qid))
    failing = {path: hits for path, hits in app_hits.items() if len(hits) >= FAIL_HITS_PER_FILE}
    return failing, dict(warn_hits)


def load_allowlist(path: Path) -> frozenset[str]:
    """Read allowlisted paths (one per line, ``#`` starts a comment).

    Args:
        path: Allowlist file.

    Returns:
        Repository-relative POSIX paths.
    """

    if not path.is_file():
        return frozenset()
    entries = (line.split("#", 1)[0].strip() for line in path.read_text(encoding="utf-8").splitlines())
    return frozenset(entry for entry in entries if entry)


def main(argv: list[str] | None = None) -> int:
    """Scan tracked files and report gold-phrase hits.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 when no application file fails (or ``--report-only``); 1 otherwise.
    """

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)
    phrases = load_gold_phrases(PRIVATE_DIR)
    if not phrases:
        print("gold_literals skipped=no_private_gold")
        return 0
    read = lambda path: (REPO / path).read_text(encoding="utf-8", errors="replace")  # noqa: E731
    app_texts = {path: read(path) for path in tracked_files(APP_ROOTS, exclude_tests=True)}
    warn_texts = {path: read(path) for path in tracked_files(WARN_ROOTS, exclude_tests=False)}
    failing, warnings = scan(app_texts, warn_texts, phrases, load_allowlist(ALLOWLIST))
    for path, hits in sorted(failing.items()):
        print(f"FAIL {path} hits={len(hits)}")
        for hit in sorted(hits, key=lambda item: item.line):
            print(f"  hit {hit.path}:{hit.line} set={hit.set_name} id={hit.question_id}")
    for path, hits in sorted(warnings.items()):
        print(f"WARN {path} hits={len(hits)}")
    print(
        f"gold_literals phrases={len(phrases)} app_files={len(app_texts)}"
        f" failing_files={len(failing)} warn_files={len(warnings)}"
    )
    if failing and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

If ruff rejects the `read = lambda` line (E731 is suppressed by the
`noqa`, but your config may flag it differently), replace it with a small
nested `def _read(path: str) -> str:` with a docstring. Keep everything
else.

Create `scripts/gold_literal_allowlist.txt` with exactly:

```text
# Paths exempt from scripts/check_gold_literals.py (one per line, then "# reason").
apps/agents/src/smart_rag_agents/prompts/answer_v4.md  # frozen historical prompt; edits are forbidden
apps/agents/src/smart_rag_agents/prompts/answer_v5.md  # frozen historical prompt; edits are forbidden
```

## Step 5 - `tests/unit/test_check_gold_literals.py` (exact code)

```python
"""Unit tests for the gold-literal guard in ``scripts/check_gold_literals.py``."""

from __future__ import annotations

from scripts.check_gold_literals import load_allowlist, normalize_source, scan


def test_regex_escapes_are_stripped() -> None:
    """A whitespace regex still matches the plain phrase."""

    assert "alpha beta gamma" in normalize_source(r'X = re.compile(r"(?i)alpha\s+beta\s+gamma")')


def test_rare_phrases_fail_and_common_phrases_are_ignored() -> None:
    """Two rare hits fail a file; a phrase in three files is vocabulary."""

    phrases = {
        "alpha beta gamma": ("set-a", "q1"),
        "delta epsilon zeta": ("set-a", "q2"),
        "common words here": ("set-b", "q3"),
    }
    app = {
        "pkg/one.py": 'A = r"alpha\\s+beta\\s+gamma"\nB = "delta epsilon zeta"\nC = "common words here"\n',
        "pkg/two.py": '"common words here"\n',
        "pkg/three.py": '"common words here"\n',
    }
    failing, warnings = scan(app, {}, phrases, frozenset())
    assert list(failing) == ["pkg/one.py"]
    assert {hit.question_id for hit in failing["pkg/one.py"]} == {"q1", "q2"}
    assert warnings == {}


def test_single_hit_and_allowlist_do_not_fail() -> None:
    """One rare hit, or an allowlisted path, never fails."""

    phrases = {"alpha beta gamma": ("s", "q1"), "delta epsilon zeta": ("s", "q2")}
    app = {
        "pkg/one.py": '"alpha beta gamma"\n',
        "pkg/old.md": "alpha beta gamma and delta epsilon zeta\n",
    }
    failing, _ = scan(app, {}, phrases, frozenset({"pkg/old.md"}))
    assert failing == {}


def test_warn_roots_never_fail() -> None:
    """Test files are reported as warnings only."""

    phrases = {"alpha beta gamma": ("s", "q1"), "delta epsilon zeta": ("s", "q2")}
    failing, warnings = scan(
        {}, {"tests/unit/t.py": "alpha beta gamma delta epsilon zeta"}, phrases, frozenset()
    )
    assert failing == {}
    assert len(warnings["tests/unit/t.py"]) == 2


def test_allowlist_parsing(tmp_path) -> None:
    """Comments and blank lines are ignored."""

    path = tmp_path / "allow.txt"
    path.write_text("# header\n\npkg/a.md  # frozen\n", encoding="utf-8")
    assert load_allowlist(path) == frozenset({"pkg/a.md"})
```

Run and record the current contamination (report-only, because G1
removes it):

```powershell
uv run python -m pytest tests/unit/test_check_gold_literals.py -q
uv run python scripts/check_gold_literals.py --report-only > .private-eval/runs/g0-gold-literals.txt
Select-String -Path .private-eval/runs/g0-gold-literals.txt -Pattern '^(FAIL|gold_literals)'
```

Expected (measured 2026-10-06 on `main` plus the parked work; on clean
`main` the numbers are a little lower): `FAIL` lines for
`packages/core/src/smart_rag_core/retrieval/rerank.py` (about 40 hits),
`packages/core/src/smart_rag_core/query_answer/generate_grounded.py`
(about 25-30), and `packages/core/src/smart_rag_core/query_answer/format_shape.py`
(2). No `FAIL` for `answer_v4.md` or `answer_v5.md` (allowlisted). Put
only the `FAIL ... hits=N` lines and the summary line into the report.

## Step 6 - Cursor rule (exact content)

Create `.cursor/rules/80-general-fix-policy.mdc`:

```markdown
---
description: Answer-quality fixes must be general; never encode eval questions or gold answers in code or prompts
alwaysApply: true
---

# General Fixes Only

- Never add code, regexes, constants, prompt bullets, or test names that mention a specific eval question, gold phrase, book page, book-specific term, or eval set id.
- A retrieval or answer change is allowed only when the stage report (`scripts/eval_stage_loss.py`) shows the same loss pattern in at least 3 failed questions across at least 2 different sets, and the change works for any document.
- Run `uv run python scripts/check_gold_literals.py` before every commit that touches `packages/` or `apps/`; it must exit 0.
- Tune and debug only on the dev set. The sealed holdout runs only for the baseline and the final acceptance; never read its per-question results.
- If a change does not lower its target stage count on the dev set, revert it. Do not fix forward with new special cases.
- Older tuned sets are not targets. Do not add code to win back their scores.
- See `docs/runbooks/answer-quality-repair-loop.md` for the loop and commands.
```

## Step 7 - Docs

### 7a. `docs/runbooks/answer-quality-repair-loop.md` (new)

Front matter (same keys as other docs):

```markdown
---
title: Answer-quality repair loop
owner: engineering-lead
status: draft
last-reviewed: <TODAY yyyy-MM-dd>
audience: eng, reviewers
---
```

Write these sections, in this order, in plain prose with the commands
copied from `00-rules-and-commands.md`:

1. `# Answer-quality repair loop` - one paragraph: why fixes tuned to one
   set did not transfer (scores near 60% on every fresh set), and that
   this runbook is the only allowed way to change answer quality.
2. `## Prerequisites` - Compose stack up, `api` image rebuilt from the
   branch, `.private-eval/eval-credentials.json`,
   `OPERATOR_SUPABASE_DB_URL` in `.env` or `.env.compose` (never print it).
3. `## The loop` - this Mermaid diagram, then one sentence per node:

   ```mermaid
   flowchart TD
     runDev["Run dev set with stage export"] --> stageReport["Stage-loss report"]
     stageReport --> pickStage["Pick the stage with the most losses"]
     pickStage --> pattern{"Same pattern in 3+ questions across 2+ sets?"}
     pattern -->|no| collect["Collect more failures; change nothing"]
     pattern -->|yes| generalFix["Write one general fix plus tests"]
     generalFix --> guard["check_gold_literals exits 0"]
     guard --> rebuild["Rebuild api image and probe"]
     rebuild --> rerunDev["Rerun dev set"]
     rerunDev --> compare{"Target stage count went down?"}
     compare -->|no| revert["Revert the commit"]
     compare -->|yes| keep["Keep; record counts in the evidence doc"]
     keep --> holdoutGate["Holdout only at plan acceptance"]
   ```

4. `## Stage definitions` - the eight stages from the
   `scripts/eval_stage_loss.py` docstring, and the three removal causes
   (`salvage_overwrite`, `refused_after_draft`, `trimmed_or_rewritten`).
5. `## Commands` - live run, stage report, subset run, gold-literal guard.
6. `## Rules` - the six bullets of `.cursor/rules/80-general-fix-policy.mdc`
   in prose, plus: "Write a new dev set when the current one has been used
   for more than three fix cycles; retire the holdout into dev after the
   acceptance run."
7. `## Writing a new question set` - the rules from Step 8b below (no
   private content; describe the rules only).
8. `## Failure modes and troubleshooting` - at least: stale image (probe
   prints `MISSING`), `blocked=missing OPERATOR_SUPABASE_DB_URL`,
   checkpoint query column error (drop the `ORDER BY`), stage report shows
   many `5_unknown_no_checkpoint` (run used a different database), guard
   prints `skipped=no_private_gold` (expected in CI).
9. `## Security` - private files stay under `.private-eval/`; reports
   carry counts and ids only.
10. `## Related` - links to `../adr/ADR-general-answer-quality.md` and
    `../evaluation/GENERAL_ANSWER_QUALITY_2026-10.md`.

### 7b. `docs/adr/ADR-general-answer-quality.md` (new)

Front matter: `title: ADR - General answer-quality repair`,
`adr_id: ADR-general-answer-quality`, `status: proposed`,
`owner: engineering-lead`, `last-reviewed: <TODAY>`,
`audience: engineering, reviewers`. Sections and required content:

- `## Status` - proposed; becomes accepted when the user accepts G5.
- `## Context` - every fresh set scored about 60%; on 130 first-time
  facts the draft held 104 and the release 80; 13 correct drafts were
  overwritten by question-specific salvages; 13 correct claims were
  rejected by the verifier; salvages repaired 2. Earliest-stage losses on
  275 facts over 6 first-time runs: generation 100, rerank/select 28,
  retrieval 9, fusion pool 5, ingestion 1.
- `## Decision` - numbered:
  1. Delete question-specific salvage, promotion, and seed code and the
     matching prompt bullets (`answer_v6`). Keep only structural repairs:
     named code definition, named table block, requested shape.
  2. A verifier "unsupported" verdict does not remove a fact claim whose
     normalized text is a verbatim substring (at least 12 characters) of
     a cited passage.
  3. Optional (G3, only if the stage report justifies it): one
     `locate_v1` gpt-4o-mini call before the answer call, recorded under
     the existing `usage_kind = "answer"` so no migration is needed, and
     skipped when it would consume the answer-stage reserve.
  4. PDF reflow keeps line breaks and indentation for monospace code
     lines and rebuilds captioned (or page-continued) tables as Markdown
     pipe tables from line geometry (`parser_v1_pdf_reflow_v5`); the
     prose splitter keeps paragraphs with single newlines whole up to
     536 tokens and otherwise splits them at line ends, repeating a pipe
     table's header (`chunking_v3`).
  5. Fixed measurement loop with dev40 and sealed holdout40 and a stop
     rule (see the runbook).
- `## Alternatives considered` - a larger model (rejected: user requires
  gpt-4o-mini); keeping salvages and adding more (rejected: does not
  transfer); a second verifier call (rejected: `MAX_VERIFIER_CALLS = 1`
  contract); a new `usage_kind` for locate (rejected: needs a migration of
  `app.llm_usage.llm_usage_kind_allowed`).
- `## Acceptance targets` - copy the six numbered targets from
  `G5-acceptance-and-ship.md` section "Acceptance targets" word for word.
- `## Consequences` - scores on older tuned sets drop; latency p90 may
  grow by up to 5 s if G3 runs; re-ingest needed for G4 (G4b).
- `## Rollback` - revert the packet commits; for G4 also follow the
  re-ingest rollback in G4b.
- `## Approvals recorded` - "gpt-4o-mini only; up to 2 answer-stage calls
  per question (user, <TODAY>)."

### 7c. `docs/evaluation/GENERAL_ANSWER_QUALITY_2026-10.md` (new)

Front matter as above (`status: draft`). Sections: `# General
answer-quality repair evidence`, `## Sets` (sizes and kind mix only),
`## Baseline (G0)` (the two tables filled in Step 10), `## After G1a`,
`## After G1b`, `## After G2`, `## After G3`, `## After G4`, `## Acceptance (G5)` (each
"not run yet" until its packet fills it). Counts only.

### 7d. Index rows

Add to `docs/README.md` (in the runbooks, adr, and evaluation groups that
already exist, matching the neighbouring rows):

```markdown
| [runbooks/answer-quality-repair-loop.md](./runbooks/answer-quality-repair-loop.md) | engineering-lead | draft | <TODAY> | eng, reviewers |
| [adr/ADR-general-answer-quality.md](./adr/ADR-general-answer-quality.md) | engineering-lead | proposed | <TODAY> | eng, reviewers |
| [evaluation/GENERAL_ANSWER_QUALITY_2026-10.md](./evaluation/GENERAL_ANSWER_QUALITY_2026-10.md) | engineering-lead | draft | <TODAY> | eng, reviewers |
```

Add to `docs/adr/README.md`:

```markdown
| ADR-general-answer-quality | proposed | answer quality | [ADR-general-answer-quality.md](./ADR-general-answer-quality.md) |
```

If the existing `docs/adr/README.md` rows use a different link or phase
style, copy the neighbouring row's style exactly.

## Step 8 - New private sets (dev40 and holdout40)

### 8a. Page dumps (private script, exact code)

Create `.private-eval/make_set_dumps.py`:

```python
"""Dump book pages by kind and pick pages for dev40 and holdout40.

Private operator helper (gitignored). Reads the current book version from
``.private-eval/ingest-ids.json``, writes one text dump per page under
``.private-eval/_sets_2026-10_dumps/`` and ``PICKS.json`` with a seeded,
disjoint page choice for the two sets. Prints counts only.
"""

from __future__ import annotations

import json
import random
import re
from collections import defaultdict
from pathlib import Path

import psycopg

ROOT = Path(".private-eval/_sets_2026-10_dumps")
SEED = 20261006
FIRST_BODY_PAGE = 14
LAST_BODY_PAGE = 336
WANT = {"code": 14, "table": 12, "text": 14}
CODE_RE = re.compile(r"\b(?:def|class|async def)\s+\w+|\bimport\s+\w+|```|@tool|BaseModel")
TABLE_RE = re.compile(r"\bTable\s+\d+-\d+")


def load_env() -> dict[str, str]:
    """Parse ``.env`` then ``.env.compose``.

    Returns:
        Merged key to value mapping.
    """

    values: dict[str, str] = {}
    for name in (".env", ".env.compose"):
        path = Path(name)
        if not path.is_file():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    """Write page dumps, INDEX.txt, and PICKS.json."""

    version_id = json.loads(Path(".private-eval/ingest-ids.json").read_text(encoding="utf-8"))["version_id"]
    env = load_env()
    with psycopg.connect(env["OPERATOR_SUPABASE_DB_URL"], connect_timeout=30) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            """
            SELECT page_number, raw_text
            FROM app.document_chunks
            WHERE version_id = %s::uuid AND deleted_at IS NULL
              AND parent_chunk_id IS NOT NULL AND page_number IS NOT NULL
            ORDER BY page_number, chunk_index
            """,
            (version_id,),
        ).fetchall()
    by_page: dict[int, list[str]] = defaultdict(list)
    for page, text in rows:
        by_page[int(page)].append(str(text))
    ROOT.mkdir(parents=True, exist_ok=True)
    kinds: dict[str, list[int]] = {"code": [], "table": [], "text": []}
    for page in range(FIRST_BODY_PAGE, LAST_BODY_PAGE + 1):
        blob = "\n\n".join(by_page.get(page, []))
        if len(blob) < 400:
            continue
        kind = "table" if TABLE_RE.search(blob) else "code" if CODE_RE.search(blob) else "text"
        kinds[kind].append(page)
        (ROOT / f"{kind}-{page:03d}.txt").write_text(f"# page {page} kind={kind}\n\n{blob}\n", encoding="utf-8")
    rng = random.Random(SEED)
    picks: dict[str, dict[str, list[int]]] = {"dev": {}, "holdout": {}, "spare": {}}
    for kind, pages in kinds.items():
        shuffled = pages[:]
        rng.shuffle(shuffled)
        n = WANT[kind]
        picks["dev"][kind] = sorted(shuffled[:n])
        picks["holdout"][kind] = sorted(shuffled[n : 2 * n])
        picks["spare"][kind] = shuffled[2 * n :]
    (ROOT / "PICKS.json").write_text(json.dumps(picks, indent=2) + "\n", encoding="utf-8")
    print({kind: len(pages) for kind, pages in kinds.items()})
    print({name: {k: len(v) for k, v in group.items()} for name, group in picks.items()})


if __name__ == "__main__":
    main()
```

```powershell
$env:PYTHONIOENCODING = "utf-8"
.venv\Scripts\python.exe .private-eval/make_set_dumps.py
```

If a kind has fewer than `2 * WANT[kind]` pages (likely for `table`),
the holdout gets fewer of that kind; fill the gap from `spare.text`
pages so each set still has 40 questions. Record the final mix per set.

### 8b. Write the questions (by hand, reading the dumps)

Write `.private-eval/dev40-2026-10-v1.json` (ids `d01`-`d40`) from the
`dev` pages and `.private-eval/holdout40-2026-10-v1.json` (ids
`h01`-`h40`) from the `holdout` pages. One question per page. Format is
the gold schema in `00-rules-and-commands.md`. Rules:

1. **Prompt prefix.** Copy the exact opening words of the `prompt` of the
   first item in `.private-eval/fresh30-2026-10-06-v1.json` up to and
   including the book title and the comma (it starts with
   `In the company document `). Every prompt starts with that prefix and
   contains `Use only that document.`
2. **Templates** (replace `<...>`; paraphrase, do not copy page
   sentences into the question):
   - text: `<PREFIX> <question in your own words>? Use only that document. Give the exact wording, name, or code fragment from the page.`
   - code: `<PREFIX> reproduce the <function or class name> <function|class> that <what it does, paraphrased> as a fenced Python code block (not a prose paraphrase). Use only that document.`
   - table: `<PREFIX> reproduce Table <N-M> (<table title>) as a Markdown pipe table including the <row label A> and <row label B> rows. Use only that document.`
3. **Facts.** 1 or 2 facts per question. Each `canonical` phrase is an
   exact span copied from the dump: 2 to 10 words for text; for code, one
   source line or part of one line (for example a `def name(args)`
   header or one assignment); for tables, one cell's text. Never span two
   lines or two cells (the scorer does not collapse whitespace).
4. **New facts only.** A canonical phrase must not appear in, or contain,
   any canonical phrase of any earlier `.private-eval/*v1.json` file
   (the validator checks this). A page may be reused; the fact may not.
5. **Not in the question.** The canonical phrase must not appear in the
   prompt.
6. **Answerable.** The fact must be on that page in the dump. Skip a page
   whose only facts are already used and take the next page of the same
   kind from `spare`.
7. **Mix.** Each set: about 14 code, up to 12 table, the rest text,
   40 total.

### 8c. Validator (private script, exact code)

Create `.private-eval/validate_new_set.py`:

```python
"""Validate a new private gold set against the stored book and older sets.

Private operator helper (gitignored). Prints counts and ``FAIL <id>
<reason>`` lines only; never prints prompts or phrases.

Example:
    ``.venv/Scripts/python.exe .private-eval/validate_new_set.py
    --set .private-eval/dev40-2026-10-v1.json
    --other .private-eval/holdout40-2026-10-v1.json``
"""

from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import Counter
from pathlib import Path

import psycopg

ID_RE = re.compile(r"^[dh]\d{2}$")


def norm(text: str) -> str:
    """Normalize like the scorer and collapse whitespace.

    Args:
        text: Any text.

    Returns:
        Normalized text.
    """

    return " ".join(unicodedata.normalize("NFKC", html.unescape(text)).casefold().split())


def load_env() -> dict[str, str]:
    """Parse ``.env`` then ``.env.compose``.

    Returns:
        Merged mapping.
    """

    values: dict[str, str] = {}
    for name in (".env", ".env.compose"):
        path = Path(name)
        if path.is_file():
            for raw in path.read_text(encoding="utf-8").splitlines():
                line = raw.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def older_phrases(exclude: set[Path]) -> set[str]:
    """Collect normalized canonical phrases of every older private set.

    Args:
        exclude: Resolved paths of the new sets.

    Returns:
        Normalized phrases.
    """

    found: set[str] = set()
    for path in Path(".private-eval").glob("*v1.json"):
        if path.resolve() in exclude:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for row in data if isinstance(data, list) else []:
            for fact in (row.get("facts") or []) if isinstance(row, dict) else []:
                for phrase in fact.get("canonical") or []:
                    found.add(norm(str(phrase)))
    return {item for item in found if item}


def main() -> int:
    """Validate the set; exit 1 on any failure.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--set", type=Path, required=True)
    parser.add_argument("--other", type=Path, default=None)
    args = parser.parse_args()
    raw = args.set.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        print("FAIL file utf8_bom")
        return 1
    items = json.loads(raw.decode("utf-8"))
    template = json.loads(Path(".private-eval/fresh30-2026-10-06-v1.json").read_text(encoding="utf-8"))[0]["prompt"]
    prefix = template[: template.index(",") + 1]
    exclude = {args.set.resolve()} | ({args.other.resolve()} if args.other else set())
    old = older_phrases(exclude)
    other_pages: set[int] = set()
    if args.other and args.other.is_file():
        other_pages = {int(row["page"]) for row in json.loads(args.other.read_text(encoding="utf-8"))}
    version_id = json.loads(Path(".private-eval/ingest-ids.json").read_text(encoding="utf-8"))["version_id"]
    with psycopg.connect(load_env()["OPERATOR_SUPABASE_DB_URL"], connect_timeout=30) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            "SELECT page_number, raw_text FROM app.document_chunks"
            " WHERE version_id = %s::uuid AND deleted_at IS NULL AND page_number IS NOT NULL",
            (version_id,),
        ).fetchall()
    page_text: dict[int, str] = {}
    for page, text in rows:
        page_text[int(page)] = page_text.get(int(page), "") + " " + norm(str(text))
    failures: list[str] = []
    ids = [str(row.get("id")) for row in items]
    if len(items) != 40:
        failures.append(f"FAIL set size={len(items)}")
    if len(set(ids)) != len(ids):
        failures.append("FAIL set duplicate_ids")
    for row in items:
        qid = str(row.get("id"))
        prompt = str(row.get("prompt") or "")
        if not ID_RE.match(qid):
            failures.append(f"FAIL {qid} bad_id")
        if row.get("kind") not in {"code", "table", "text"}:
            failures.append(f"FAIL {qid} bad_kind")
        if not prompt.startswith(prefix) or "Use only that document." not in prompt:
            failures.append(f"FAIL {qid} prompt_template")
        page = int(row.get("page") or 0)
        if page in other_pages:
            failures.append(f"FAIL {qid} page_shared_with_other_set")
        facts = row.get("facts") or []
        if not 1 <= len(facts) <= 2:
            failures.append(f"FAIL {qid} fact_count")
        for fact in facts:
            for phrase in fact.get("canonical") or []:
                key = norm(str(phrase))
                if "\n" in str(phrase) or not 4 <= len(key) <= 120:
                    failures.append(f"FAIL {qid} {fact.get('id')} phrase_shape")
                if key in norm(prompt):
                    failures.append(f"FAIL {qid} {fact.get('id')} phrase_in_prompt")
                if key not in page_text.get(page, ""):
                    failures.append(f"FAIL {qid} {fact.get('id')} not_on_page")
                if any(key in item or item in key for item in old if len(item) >= 4):
                    failures.append(f"FAIL {qid} {fact.get('id')} reused_fact")
    print("kinds", dict(Counter(str(row.get("kind")) for row in items)))
    for line in failures:
        print(line)
    print(f"failures={len(failures)}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
```

The `not_on_page` check uses the page's stored chunks. A fact whose chunk
is filed under the neighbouring page fails; move the question's `page`
to that page number or pick another fact.

```powershell
.venv\Scripts\python.exe .private-eval/validate_new_set.py --set .private-eval/dev40-2026-10-v1.json --other .private-eval/holdout40-2026-10-v1.json
.venv\Scripts\python.exe .private-eval/validate_new_set.py --set .private-eval/holdout40-2026-10-v1.json --other .private-eval/dev40-2026-10-v1.json
```

Pass: both print `failures=0`. Fix the questions until they do.

Seal the holdout and record pages:

```powershell
(Get-FileHash .private-eval/holdout40-2026-10-v1.json -Algorithm SHA256).Hash | Set-Content -Encoding ascii .private-eval/holdout40-2026-10-v1.sha256
.venv\Scripts\python.exe -c "import json,pathlib; p=pathlib.Path('.private-eval/used-pages.txt'); used={int(x) for x in p.read_text().strip().split(',') if x}; new={int(r['page']) for f in ('dev40-2026-10-v1.json','holdout40-2026-10-v1.json') for r in json.loads(pathlib.Path('.private-eval',f).read_text(encoding='utf-8'))}; p.write_text(','.join(str(x) for x in sorted(used|new))+'\n'); print('used_pages', len(used|new))"
```

From now on do not open the holdout file again until G5.

## Step 9 - Lint, types, tests, docs, commit

```powershell
uv run python -m ruff format scripts/eval_stage_loss.py scripts/check_gold_literals.py tests/unit/test_eval_stage_loss.py tests/unit/test_check_gold_literals.py
uv run python scripts/check.py --tier lint
uv run python scripts/check.py --tier types
uv run python -m pytest tests/unit/test_eval_stage_loss.py tests/unit/test_check_gold_literals.py -q
uv run python scripts/check.py --tier docs
```

Commit (the guard is not gating yet; G1 makes it exit 0):

```powershell
git add scripts/eval_stage_loss.py scripts/check_gold_literals.py scripts/gold_literal_allowlist.txt
git add tests/unit/test_eval_stage_loss.py tests/unit/test_check_gold_literals.py .cursor/rules/80-general-fix-policy.mdc
git add docs/runbooks/answer-quality-repair-loop.md docs/adr/ADR-general-answer-quality.md docs/evaluation/GENERAL_ANSWER_QUALITY_2026-10.md docs/README.md docs/adr/README.md
git commit -m "feat(eval): stage-loss report, gold-literal guard, and repair-loop runbook (G0)"
git push
gh pr checks --watch --fail-fast
```

## Step 10 - Baselines (clean `main` code)

The running `api` image may contain the parked fresh-30 code. Rebuild
from this branch (whose runtime code equals `main`):

```powershell
docker compose --env-file .env.compose -f docker-compose.yml -f docker-compose.packet8.yml up -d --build --wait api
Invoke-RestMethod http://127.0.0.1:8000/health/ready | ConvertTo-Json -Compress
```

Run the probe from `00-rules-and-commands.md`: all three lines print
`MISSING` (expected before G1).

Run dev40 with `$run = "dev40-g0-baseline"` using the live command, then
the stage report. Then the holdout with `$run = "holdout40-g0-baseline"`,
`--gold .private-eval/holdout40-2026-10-v1.json`, and the stage report
with `--aggregate-only`. Do not open the holdout `answers.json` or
`summary.json` beyond the aggregate line:

```powershell
.venv\Scripts\python.exe -c "import json; s=json.load(open('.private-eval/runs/holdout40-g0-baseline/summary.json',encoding='utf-8')); o=s['outcomes']; print('holdout strict_pass', sum(bool(x['strict_pass']) for x in o), '/', len(o))"
```

Fill `## Baseline (G0)` in `docs/evaluation/GENERAL_ANSWER_QUALITY_2026-10.md`
with two tables (dev40, holdout40), rows = the eight stages plus
`strict passes`, values = counts. Commit:

```powershell
git add docs/evaluation/GENERAL_ANSWER_QUALITY_2026-10.md
git commit -m "docs(eval): G0 dev40 and holdout40 baselines"
git push
gh pr checks --watch --fail-fast
```

## Done when

- [ ] `wip/fresh30-postfix` holds the parked work (not pushed); branch
      `fix/general-answer-quality` has no modified tracked files before
      Step 2; draft PR exists.
- [ ] `tests/unit/test_eval_stage_loss.py` 7 passed;
      `tests/unit/test_check_gold_literals.py` 5 passed.
- [ ] `check_gold_literals.py --report-only` output recorded (FAIL lines
      and summary only).
- [ ] Rule, runbook, ADR, evidence doc, and index rows exist; docs tier
      exits 0.
- [ ] Both new sets validate with `failures=0`; holdout sealed;
      `used-pages.txt` updated.
- [ ] Image rebuilt; dev40 and holdout40 baselines ran; both stage
      reports printed; evidence doc filled with counts only.
- [ ] Lint, types, unit tests for the new files pass; PR checks green.

## Commit messages

```text
docs(plan): general answer-quality repair plan G0-G5
feat(eval): stage-loss report, gold-literal guard, and repair-loop runbook (G0)
docs(eval): G0 dev40 and holdout40 baselines
```

## Do not

- Do not push `wip/fresh30-postfix` or merge it.
- Do not change any runtime code under `packages/` or `apps/` in G0.
- Do not print or commit questions, phrases, answers, or chunk text.
- Do not reread the holdout after sealing it.
