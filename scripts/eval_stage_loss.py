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
from typing import Any, cast

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
        for item in cast(list[object], value):
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
    return [
        cast(Mapping[str, Any], item)
        for item in cast(list[object], raw)
        if isinstance(item, dict)
    ]


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

        return any(
            key in text_by_id.get(chunk_id, "")
            for chunk_id in chunk_ids
            for key in keys
        )

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
        loaded: object = json.loads(stages_path.read_text(encoding="utf-8"))
        root = cast(dict[str, object], loaded) if isinstance(loaded, dict) else {}
        runs = root.get("runs")
        if isinstance(runs, dict):
            exported = cast(dict[str, object], runs)
    result: dict[str, StageIds] = {}
    for qid, row in answers.items():
        stage = row.get("stages")
        stage_map = cast(dict[str, object], stage) if isinstance(stage, dict) else {}
        ids = stage_ids(stage_map)
        fallback = exported.get(qid)
        if not ids.selected and isinstance(fallback, dict):
            ids = stage_ids(cast(dict[str, object], fallback))
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

    stage_chunk_ids = sorted(
        {cid for ids in stages_by_id.values() for cid in ids.candidates}
    )
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
                decoded: object = serde.loads_typed((kind, bytes(blob)))
                if not isinstance(decoded, dict):
                    continue
                payload = cast(dict[str, Any], decoded)
                node = str(task_path).split(",")[-1].strip()
                if node == "generate_answer":
                    draft = payload
                elif node == "verify_answer":
                    final = payload
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
        id_map = cast(Mapping[str, object], report["question_ids_by_stage"])
        raw_ids = id_map.get(stage)
        ids = (
            [str(item) for item in cast(list[object], raw_ids)]
            if isinstance(raw_ids, list)
            else []
        )
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

    with psycopg.connect(
        env["OPERATOR_SUPABASE_DB_URL"], connect_timeout=20
    ) as connection:
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
            report = {
                key: value
                for key, value in report.items()
                if key != "question_ids_by_stage"
            }
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
