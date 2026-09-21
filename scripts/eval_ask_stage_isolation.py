"""Four-arm isolation: prepare gold, exam retrieve, and assign first-fail stages.

Evaluator-only. Private files stay under ``.private-eval/``. Prints counts
and the named decision-gate branch. Never prints questions or gold phrases.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_agents.query.runtime.adapters import (  # noqa: E402
    DsnBm25Retriever,
    context_loader,
)
from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    AskRegressionConfigError,
    load_private_gold,
)
from smart_rag_core.gateways.embedding import create_embedding_gateway  # noqa: E402
from smart_rag_core.retrieval.cache_store import RetrievalCacheMode  # noqa: E402
from smart_rag_core.retrieval.coverage import CoverageDecision  # noqa: E402
from smart_rag_core.retrieval.frozen_profile import (  # noqa: E402
    LONG_DOCUMENT_PROFILE_ID,
)
from smart_rag_core.retrieval.fusion import FusionError  # noqa: E402
from smart_rag_core.retrieval.hybrid_run import HybridRetriever  # noqa: E402
from smart_rag_core.settings import SharedSettings  # noqa: E402

from scripts.eval_ask_oracle_context import (  # noqa: E402
    _json_mapping,
    _load_credentials_email,
    lookup_eval_caller,
    resolve_eval_user_id,
)
from scripts.pdf_eval_cli import apply_merged_env, operator_url  # noqa: E402
from scripts.pdf_eval_runtime import (  # noqa: E402
    _DsnChannelMarker,
    bind_live_rerank,
    load_profile_for_eval,
    query_profile_for_retrieve,
)
from tests.contract.integration_support import packet8_paradedb_url  # noqa: E402

STAGES = (
    "label",
    "profile/route",
    "scope/selector",
    "index",
    "channel_candidate",
    "fusion/rerank",
    "context_fit",
    "coverage/correction",
    "answer",
    "verifier/release",
    "deadline",
    "metric_only",
)
_PRIVATE = ".private-eval"


def _require_private(path: Path) -> Path:
    """Reject paths outside the gitignored private tree.

    Args:
        path: Caller path.

    Returns:
        Resolved path.

    Raises:
        AskRegressionConfigError: Path is not private.
    """

    resolved = path.resolve()
    if _PRIVATE not in {part.casefold() for part in resolved.parts}:
        raise AskRegressionConfigError("isolation files must live under .private-eval")
    return resolved


def _write_json(path: Path, payload: object) -> None:
    """Write pretty JSON to a private path.

    Args:
        path: Destination.
        payload: JSON-serializable object.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> object:
    """Load JSON from a private path.

    Args:
        path: Source file.

    Returns:
        Parsed JSON.
    """

    return json.loads(_require_private(path).read_text(encoding="utf-8"))


def strip_title_clause(prompt: str, title: str) -> str:
    """Remove the book-title clause from one question for Arm A-prime.

    Args:
        prompt: Original question.
        title: Canonical document title. Never logged.

    Returns:
        Prompt with the title substring removed and whitespace collapsed.
    """

    cleaned = prompt
    if title.strip():
        cleaned = re.sub(re.escape(title.strip()), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,;:-")
    return cleaned


def prepare_gold(
    *,
    gold_path: Path,
    slice_path: Path,
    title_path: Path,
    slice_gold_out: Path,
    aprime_out: Path,
) -> dict[str, int]:
    """Materialize the 12-question slice and title-stripped A-prime gold.

    Args:
        gold_path: 100-question private gold.
        slice_path: Isolation-slice IDs and chunk IDs.
        title_path: Canonical title text file.
        slice_gold_out: Written 12-question gold.
        aprime_out: Written title-stripped gold.

    Returns:
        Count-only summary.
    """

    questions = load_private_gold(_require_private(gold_path))
    slice_rows = _load_json(slice_path)
    if not isinstance(slice_rows, list):
        raise AskRegressionConfigError("slice must be a JSON array")
    wanted = {
        str(_json_mapping(item).get("id") or "")
        for item in cast(list[object], slice_rows)
        if isinstance(item, dict)
    }
    title = _require_private(title_path).read_text(encoding="utf-8").strip()
    selected = [item for item in questions if item.question_id in wanted]
    if len(selected) != 12:
        raise AskRegressionConfigError(f"slice_count_{len(selected)}")
    slice_gold = []
    aprime = []
    stripped = 0
    for item in selected:
        facts = [
            {
                "id": fact.fact_id,
                "canonical": list(fact.canonical_phrases),
                "aliases": list(fact.approved_aliases),
            }
            for fact in item.facts
        ]
        slice_gold.append(
            {"id": item.question_id, "question": item.prompt, "facts": facts}
        )
        stripped_prompt = strip_title_clause(item.prompt, title)
        if stripped_prompt != item.prompt:
            stripped += 1
        aprime.append(
            {"id": item.question_id, "question": stripped_prompt, "facts": facts}
        )
    _write_json(slice_gold_out, slice_gold)
    _write_json(aprime_out, aprime)
    return {
        "slice_questions": len(slice_gold),
        "title_stripped": stripped,
        "acceptance_sample_untouched": 30,
    }


def _ids_hit(channel: Sequence[object], gold: Sequence[str]) -> bool:
    """Return whether any gold ID appears in a channel list.

    Args:
        channel: Retrieved IDs.
        gold: Approved gold IDs.

    Returns:
        True on any overlap.
    """

    gold_set = {str(item) for item in gold}
    return any(str(item) in gold_set for item in channel)


def exam_retrieve(
    *,
    gold_path: Path,
    slice_path: Path,
    credentials: Path,
    out_path: Path,
    version_id: UUID,
) -> dict[str, object]:
    """Run production Hybrid retrieve with ``cold_bypass`` for one gold file.

    Args:
        gold_path: Questions to retrieve.
        slice_path: Approved gold chunk IDs.
        credentials: Evaluator credentials.
        out_path: Private ID-only report.
        version_id: Canonical version restriction.

    Returns:
        Count-only histogram inputs.

    Raises:
        RuntimeError: ParadeDB or live models are unavailable.
    """

    env = apply_merged_env()
    questions = load_private_gold(_require_private(gold_path))
    slice_rows = _load_json(slice_path)
    gold_by_id: dict[str, list[str]] = {}
    if isinstance(slice_rows, list):
        for raw in cast(list[object], slice_rows):
            row = _json_mapping(raw)
            qid = str(row.get("id") or "")
            chunks = row.get("chunk_ids")
            if qid and isinstance(chunks, list):
                gold_by_id[qid] = [str(item) for item in cast(list[object], chunks)]
    parade = packet8_paradedb_url()
    if not parade:
        raise RuntimeError("paradedb_url_missing")
    operator_dsn = operator_url(env)
    email = _load_credentials_email(credentials)
    caller = lookup_eval_caller(
        operator_dsn, resolve_eval_user_id(operator_dsn, email)
    )
    settings = SharedSettings()
    if settings.mock_model_mode:
        raise RuntimeError("mock_embeddings_not_live_hybrid")
    long_profile = load_profile_for_eval(LONG_DOCUMENT_PROFILE_ID)
    bm25 = DsnBm25Retriever(parade)
    outcomes: list[dict[str, object]] = []
    loss = Counter()
    for question in questions:
        typed_profile = query_profile_for_retrieve(question.prompt)
        wanted_profile = long_profile
        retriever = HybridRetriever(
            embedding_gateway=create_embedding_gateway(settings),
            supabase=None,
            paradedb=None,
            supabase_dsn=operator_dsn,
            dense=_DsnChannelMarker(),
            bm25=bm25,
            term=_DsnChannelMarker(),
            load_context=context_loader(operator_dsn, caller),
            rerank=bind_live_rerank(settings),  # type: ignore[arg-type]
            retrieval_profile=wanted_profile,  # type: ignore[arg-type]
        )
        gold_ids = gold_by_id.get(question.question_id, [])
        try:
            result = retriever.retrieve(
                query=question.prompt,
                caller=caller,
                profile=typed_profile,
                restrict_version_id=version_id,
                cache_mode=RetrievalCacheMode.COLD_BYPASS,
            )
        except FusionError as exc:
            loss["dense"] += 1
            loss["bm25"] += 1
            loss["term"] += 1
            loss["fused"] += 1
            loss["selected"] += 1
            outcomes.append(
                {
                    "question_id": question.question_id,
                    "gold_count": len(gold_ids),
                    "cache_mode": RetrievalCacheMode.COLD_BYPASS.value,
                    "fallback_reason": str(exc) or "fusion_error",
                    "rerank_fallback": "none",
                    "dense_count": 0,
                    "bm25_count": 0,
                    "term_count": 0,
                    "fused_count": 0,
                    "selected_count": 0,
                    "coverage": "none",
                    "refused": False,
                    "any_channel_gold": False,
                    "gold_in_dense": False,
                    "gold_in_bm25": False,
                    "gold_in_term": False,
                    "gold_in_fused": False,
                    "gold_in_selected": False,
                }
            )
            continue
        flags = {
            "dense": _ids_hit(result.dense_ids, gold_ids),
            "bm25": _ids_hit(result.bm25_ids, gold_ids),
            "term": _ids_hit(result.term_ids, gold_ids),
            "fused": _ids_hit(result.fused_ids, gold_ids),
            "selected": _ids_hit(result.selected_ids or result.ranked_ids, gold_ids),
        }
        any_channel = bool(flags["dense"] or flags["bm25"] or flags["term"])
        if gold_ids and not flags["dense"]:
            loss["dense"] += 1
        if gold_ids and not flags["bm25"]:
            loss["bm25"] += 1
        if gold_ids and not flags["term"]:
            loss["term"] += 1
        if gold_ids and not flags["fused"]:
            loss["fused"] += 1
        if gold_ids and not flags["selected"]:
            loss["selected"] += 1
        coverage = result.coverage.decision if result.coverage is not None else None
        outcomes.append(
            {
                "question_id": question.question_id,
                "gold_count": len(gold_ids),
                "cache_mode": RetrievalCacheMode.COLD_BYPASS.value,
                "fallback_reason": str(result.fallback_reason),
                "rerank_fallback": str(result.rerank_fallback or "none"),
                "dense_count": len(result.dense_ids),
                "bm25_count": len(result.bm25_ids),
                "term_count": len(result.term_ids),
                "fused_count": len(result.fused_ids),
                "selected_count": len(result.selected_ids or result.ranked_ids),
                "coverage": str(coverage) if coverage is not None else "none",
                "refused": coverage is CoverageDecision.REFUSE,
                "any_channel_gold": any_channel,
                **{f"gold_in_{name}": value for name, value in flags.items()},
            }
        )
    report = {
        "cache_mode": RetrievalCacheMode.COLD_BYPASS.value,
        "questions": len(outcomes),
        "gold_loss_histogram": dict(loss),
        "any_channel_gold": sum(
            1 for row in outcomes if bool(row["any_channel_gold"])
        ),
        "outcomes": outcomes,
        "holdout_opened": False,
    }
    _write_json(out_path, report)
    return {
        "questions": len(outcomes),
        "gold_loss_histogram": dict(loss),
        "any_channel_gold": report["any_channel_gold"],
    }


def _outcome_by_id(payload: Mapping[str, object]) -> dict[str, dict[str, object]]:
    """Index outcome rows by question id.

    Args:
        payload: Arm report.

    Returns:
        Question id to outcome mapping.
    """

    rows = payload.get("outcomes")
    if not isinstance(rows, list):
        return {}
    out: dict[str, dict[str, object]] = {}
    for raw in cast(list[object], rows):
        row = _json_mapping(raw)
        qid = str(row.get("question_id") or row.get("id") or "")
        if qid:
            out[qid] = row
    return out


def assign_stage(
    *,
    gold_count: int,
    ask: Mapping[str, object],
    exam_a: Mapping[str, object],
    exam_ap: Mapping[str, object],
    arm_b: Mapping[str, object],
    ask_ap: Mapping[str, object] | None,
) -> str:
    """Assign exactly one first-failing stage from measured fields.

    Args:
        gold_count: Approved gold chunk count.
        ask: Arm A Ask outcome plus joined stage export.
        exam_a: Exam retrieve for the titled question.
        exam_ap: Exam retrieve for the title-stripped question.
        arm_b: Oracle answer outcome.
        ask_ap: Optional Arm A-prime Ask outcome.

    Returns:
        One allow-listed stage name.
    """

    if gold_count <= 0:
        return "label"
    if bool(ask.get("deadline_failure")):
        return "deadline"
    arm_b_grounded = bool(arm_b.get("grounded_fact_pass"))
    arm_b_authorized = int(arm_b.get("authorized_gold") or 0)
    if not arm_b_grounded:
        if arm_b_authorized > 0 and str(arm_b.get("answer_status") or "") == "refused":
            return "verifier/release"
        return "answer"
    exam_fallback = str(exam_a.get("fallback_reason") or "")
    if exam_fallback == "more_than_three_variants":
        return "fusion/rerank"
    a_any = bool(exam_a.get("any_channel_gold"))
    ap_any = bool(exam_ap.get("any_channel_gold"))
    a_selected = bool(exam_a.get("gold_in_selected"))
    a_fused = bool(exam_a.get("gold_in_fused"))
    ask_empty = bool(ask.get("empty_retrieval"))
    ask_grounded = bool(ask.get("grounded_fact_pass"))
    ask_fallback = str(ask.get("fallback_reason") or ask.get("empty_retrieval") or "")
    ask_source = str(ask.get("source_resolution") or "")
    ask_route = str(ask.get("effective_route") or "")
    if ap_any and not a_any:
        return "scope/selector"
    if ask_ap is not None:
        aprime_grounded = bool(ask_ap.get("grounded_fact_pass"))
        aprime_empty = bool(ask_ap.get("empty_retrieval"))
        if ask_empty and ap_any and not aprime_empty:
            return "scope/selector"
        if aprime_grounded and not ask_grounded and ask_empty:
            return "scope/selector"
    if not a_any and not ap_any:
        if ask_source in {"none", "zero", "unscoped"} or ask_fallback == "retrieval_empty":
            return "index"
        return "channel_candidate"
    if a_any and not a_fused:
        return "fusion/rerank"
    if a_fused and not a_selected:
        return "fusion/rerank"
    if a_selected and ask_empty:
        return "context_fit"
    if a_selected and not ask_grounded:
        if bool(exam_a.get("refused")):
            return "coverage/correction"
        if int(ask.get("citation_count") or 0) == 0:
            return "context_fit"
        return "answer"
    if ask_route and ask_route.casefold() not in {"hybrid", "company_documents"}:
        return "profile/route"
    if ask_grounded:
        return "metric_only"
    return "coverage/correction"


def bind_first_fail_stage(stages: Sequence[str]) -> str:
    """Accept exactly one allow-listed first-failing stage.

    Args:
        stages: Candidate stage names for one case.

    Returns:
        The single assigned stage.

    Raises:
        RuntimeError: Zero, two, or an unknown stage would be claimed.
    """

    unique = [item for item in stages if item]
    if len(unique) != 1:
        raise RuntimeError("multiple_first_fail_stages")
    stage = unique[0]
    if stage not in STAGES:
        raise RuntimeError("invalid_stage")
    return stage


def name_gate(histogram: Mapping[str, int]) -> str:
    """Name the P06-70 decision-gate branch from the 12-row histogram.

    Args:
        histogram: First-failing stage counts.

    Returns:
        Named gate branch.
    """

    failing = {
        key: count
        for key, count in histogram.items()
        if key != "metric_only" and int(count or 0) > 0
    }
    if not failing:
        return "metric_aliases"
    buckets: dict[str, int] = {
        "answer_verifier_release": failing.get("answer", 0)
        + failing.get("verifier/release", 0),
        "scope_selector": failing.get("scope/selector", 0),
        "candidate_index": failing.get("channel_candidate", 0)
        + failing.get("index", 0),
        "fusion_rerank_selection": failing.get("fusion/rerank", 0),
        "route_determinism": failing.get("profile/route", 0),
        "deadline_budget": failing.get("deadline", 0),
    }
    majority = max(buckets.values())
    if majority >= 6:
        for name, count in buckets.items():
            if count == majority:
                return name
    earliest = next(
        (stage for stage in STAGES if failing.get(stage, 0) == max(failing.values())),
        "channel_candidate",
    )
    return f"earliest_majority_{earliest.replace('/', '_')}"


def _merge_stage_export(
    ask_rows: dict[str, dict[str, object]],
    stage_path: Path | None,
) -> None:
    """Copy measured Ask diagnostics onto Ask outcome rows.

    Args:
        ask_rows: Mutable question-id outcomes.
        stage_path: Optional stage-export JSON.
    """

    if stage_path is None:
        return
    payload = _json_mapping(_load_json(stage_path))
    runs = payload.get("runs")
    if not isinstance(runs, dict):
        return
    for key, raw in cast(dict[object, object], runs).items():
        row = ask_rows.setdefault(str(key), {})
        staged = _json_mapping(raw)
        for field in (
            "source_resolution",
            "fallback_reason",
            "effective_route",
            "retrieval_empty",
            "unknown_fields",
            "citation_count",
        ):
            if field in staged:
                row[field] = staged[field]
        if "empty_retrieval" not in row and "retrieval_empty" in staged:
            row["empty_retrieval"] = staged["retrieval_empty"]


def assign_report(
    *,
    slice_path: Path,
    ask_a: Path,
    ask_ap: Path,
    exam_a: Path,
    exam_ap: Path,
    arm_b: Path,
    out_path: Path,
    stage_a: Path | None = None,
    stage_ap: Path | None = None,
) -> dict[str, object]:
    """Assign one stage per slice question and name the gate.

    Args:
        slice_path: Isolation slice with gold counts.
        ask_a: Arm A Ask summary.
        ask_ap: Arm A-prime Ask summary.
        exam_a: Exam retrieve for titled questions.
        exam_ap: Exam retrieve for stripped questions.
        arm_b: Oracle arm.
        out_path: Private assignment report.
        stage_a: Optional Arm A stage-export JSON.
        stage_ap: Optional Arm A-prime stage-export JSON.

    Returns:
        Count-only summary including the named gate.
    """

    slice_rows = _load_json(slice_path)
    gold_counts: dict[str, int] = {}
    if isinstance(slice_rows, list):
        for raw in cast(list[object], slice_rows):
            row = _json_mapping(raw)
            qid = str(row.get("id") or "")
            if qid:
                gold_counts[qid] = int(row.get("gold_chunk_count") or 0)
    ask_a_rows = _outcome_by_id(_json_mapping(_load_json(ask_a)))
    ask_ap_rows = _outcome_by_id(_json_mapping(_load_json(ask_ap)))
    _merge_stage_export(ask_a_rows, stage_a)
    _merge_stage_export(ask_ap_rows, stage_ap)
    exam_a_rows = _outcome_by_id(_json_mapping(_load_json(exam_a)))
    exam_ap_rows = _outcome_by_id(_json_mapping(_load_json(exam_ap)))
    arm_b_rows = _outcome_by_id(_json_mapping(_load_json(arm_b)))
    missing = [
        qid
        for qid in gold_counts
        if qid not in ask_a_rows
        or qid not in exam_a_rows
        or qid not in exam_ap_rows
        or qid not in arm_b_rows
    ]
    if missing:
        raise RuntimeError(f"unmeasured_cases={len(missing)}")
    assigned: list[dict[str, object]] = []
    histogram: Counter[str] = Counter()
    for qid, gold_count in gold_counts.items():
        stage = bind_first_fail_stage(
            [
                assign_stage(
                    gold_count=gold_count,
                    ask=ask_a_rows[qid],
                    exam_a=exam_a_rows[qid],
                    exam_ap=exam_ap_rows[qid],
                    arm_b=arm_b_rows[qid],
                    ask_ap=ask_ap_rows.get(qid),
                )
            ]
        )
        histogram[stage] += 1
        assigned.append({"question_id": qid, "stage": stage})
    if len(assigned) != 12:
        raise RuntimeError(f"assignment_count_{len(assigned)}")
    gate = name_gate(histogram)
    report = {
        "rows": assigned,
        "histogram": dict(histogram),
        "gate_branch": gate,
        "holdout_opened": False,
        "acl_recheck": True,
    }
    _write_json(out_path, report)
    return {
        "rows": 12,
        "histogram": dict(histogram),
        "gate_branch": gate,
        "holdout_opened": False,
    }


def main(argv: list[str] | None = None) -> int:
    """Dispatch prepare, exam-retrieve, or assign.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` on success, ``2`` on configuration or measurement failure.
    """

    parser = argparse.ArgumentParser(description="P06-70 four-arm isolation helpers.")
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--gold", type=Path, required=True)
    prepare.add_argument("--slice", type=Path, required=True)
    prepare.add_argument("--title", type=Path, required=True)
    prepare.add_argument("--slice-gold-out", type=Path, required=True)
    prepare.add_argument("--aprime-out", type=Path, required=True)
    exam = sub.add_parser("exam-retrieve")
    exam.add_argument("--gold", type=Path, required=True)
    exam.add_argument("--slice", type=Path, required=True)
    exam.add_argument("--credentials", type=Path, required=True)
    exam.add_argument("--ids", type=Path, required=True)
    exam.add_argument("--out", type=Path, required=True)
    assign = sub.add_parser("assign")
    assign.add_argument("--slice", type=Path, required=True)
    assign.add_argument("--ask-a", type=Path, required=True)
    assign.add_argument("--ask-ap", type=Path, required=True)
    assign.add_argument("--exam-a", type=Path, required=True)
    assign.add_argument("--exam-ap", type=Path, required=True)
    assign.add_argument("--arm-b", type=Path, required=True)
    assign.add_argument("--stage-a", type=Path, default=None)
    assign.add_argument("--stage-ap", type=Path, default=None)
    assign.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            summary = prepare_gold(
                gold_path=args.gold,
                slice_path=args.slice,
                title_path=args.title,
                slice_gold_out=args.slice_gold_out,
                aprime_out=args.aprime_out,
            )
        elif args.command == "exam-retrieve":
            ids_payload = _json_mapping(_load_json(args.ids))
            version_id = UUID(str(ids_payload.get("version_id") or ""))
            summary = exam_retrieve(
                gold_path=args.gold,
                slice_path=args.slice,
                credentials=args.credentials,
                out_path=args.out,
                version_id=version_id,
            )
        else:
            summary = assign_report(
                slice_path=args.slice,
                ask_a=args.ask_a,
                ask_ap=args.ask_ap,
                exam_a=args.exam_a,
                exam_ap=args.exam_ap,
                arm_b=args.arm_b,
                out_path=args.out,
                stage_a=args.stage_a,
                stage_ap=args.stage_ap,
            )
    except (AskRegressionConfigError, RuntimeError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"blocked={exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
