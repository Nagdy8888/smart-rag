"""Private PDF agent evaluation. Does not reuse eval_judge_v1.md."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

from smart_rag_core.evaluation.holdout import HoldoutSealedError
from smart_rag_core.evaluation.private_pdf import (
    assert_holdout_path_hidden,
    development_labels_are_sealed,
    load_private_pdf_labeled_qualification,
    load_private_pdf_labeled_tuning,
    load_private_pdf_tuning_cases,
)
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_PROFILE_ID,
    UnknownRetrievalProfileError,
    load_frozen_profile,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.settings import SharedSettings

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.pdf_eval_cli import (  # noqa: E402
    apply_merged_env,
    matrix_verified,
    operator_url,
    require_live_models,
    resolve_labels_path,
)
from scripts.pdf_eval_runtime import (  # noqa: E402
    PdfEvalRuntime,
    generate_live_answer,
    judge_pdf_answer,
    load_current_chunk_ids,
    probe_infra,
    score_agent_rows,
    write_report,
)

JUDGE_PROMPT = "eval_pdf_judge_v1"


def _print_block(*lines: str) -> int:
    """Print fail-closed tokens and return 2.

    Args:
        *lines: Safe stdout lines.

    Returns:
        Process exit code 2.
    """

    for line in lines:
        print(line)
    print(f"judge_prompt={JUDGE_PROMPT}")
    print("eval_judge_v1_reused=false")
    print("holdout_opened=false")
    print(f"content_class={ContentClass.REAL_COMPANY.value}")
    return 2


def _run_split(split: str, labels: Path, ingest_ids: Path) -> int:
    """Retrieve, answer, and judge one open split.

    Args:
        split: ``development`` or ``qualification``.
        labels: Human-sealed JSON.
        ingest_ids: Ingest identity.

    Returns:
        ``0`` when aggregates were written.
    """

    ids = json.loads(ingest_ids.read_text(encoding="utf-8"))
    version_id = UUID(str(ids["version_id"]))
    if split == "qualification":
        labeled = load_private_pdf_labeled_qualification(labels)
    else:
        labeled = load_private_pdf_labeled_tuning(labels)
    if not labeled:
        return _print_block("blocked=no_scored_cases")
    settings = SharedSettings()
    env = apply_merged_env()
    supabase_url = operator_url(env)
    probed = probe_infra(supabase_url)
    if probed is None:
        return _print_block("blocked=supabase_or_paradedb_unavailable")
    runtime = PdfEvalRuntime(
        supabase_url=supabase_url,
        parade_url=probed[1],
        settings=settings,
        version_id=version_id,
        current_chunk_ids=load_current_chunk_ids(supabase_url, version_id),
        live_rerank=True,
    )
    _scores, results = runtime.retrieve_labeled(
        labeled,
        default_profile_id=HYBRID_DEFAULT_PROFILE_ID,
        long_profile_id=LONG_DOCUMENT_PROFILE_ID,
    )
    answers: list[AnswerPayload] = []
    judges: list[tuple[str, float | None]] = []
    for row, result in zip(labeled, results, strict=True):
        answer = generate_live_answer(
            settings=settings,
            query=row.question,
            result=result,
        )
        excerpts = tuple(unit.citation_text[:800] for unit in result.evidence[:8])
        judge = judge_pdf_answer(
            query=row.question,
            answer_text=answer.answer_text,
            atomic_facts=row.atomic_facts,
            excerpt_ids=tuple(str(unit.chunk_id) for unit in result.evidence),
            excerpts=excerpts,
        )
        answers.append(answer)
        judges.append(judge)
    report = score_agent_rows(labeled, results, answers, judges)
    report["split"] = split
    out_name = (
        "agent-dev-report.json" if split == "development" else "agent-qual-report.json"
    )
    write_report(Path(".private-eval") / out_name, report)
    print(f"case_count={report['case_count']}")
    print(f"citation_correctness={report['citation_correctness']}")
    print(f"citation_completeness={report['citation_completeness']}")
    print(f"routing={report['routing']}")
    print(f"mean_judge_faithfulness={report['mean_judge_faithfulness']}")
    print(f"judge_unscored_count={report['judge_unscored_count']}")
    print(f"agent_gates_pass={report['agent_gates_pass']}")
    print(f"judge_prompt={JUDGE_PROMPT}")
    print("eval_judge_v1_reused=false")
    print("holdout_opened=false")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Fail closed until freeze, human seal, and provider approval exist.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``2`` while operator gates remain open. Invalid judge output is
        ``unscored`` and is never treated as a pass.
    """

    parser = argparse.ArgumentParser(
        description="Private PDF agent eval using eval_pdf_judge_v1 only."
    )
    parser.add_argument("--split", default="development")
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--labels",
        type=Path,
        default=Path(".private-eval/eval-draft/draft.json"),
    )
    parser.add_argument(
        "--ids",
        type=Path,
        default=Path(".private-eval/ingest-ids.json"),
    )
    args = parser.parse_args(argv)
    env = apply_merged_env()
    if args.split == "holdout":
        return _print_block("blocked=holdout_sealed")
    try:
        if args.labels.is_file() or args.labels.parts:
            assert_holdout_path_hidden(args.labels)
    except HoldoutSealedError:
        return _print_block("blocked=holdout_sealed")
    if not matrix_verified(env):
        return _print_block("blocked=provider_matrix_unverified")
    if not args.live:
        return _print_block("blocked=live_agent_eval_required")
    try:
        require_live_models(env)
    except RuntimeError as error:
        return _print_block(f"blocked={error}")
    labels = resolve_labels_path(args.labels, args.ids)
    if labels.is_file():
        cases = load_private_pdf_tuning_cases(labels)
        sealed = development_labels_are_sealed(cases)
    else:
        sealed = False
    if not sealed:
        return _print_block(
            "blocked=frozen_profile_and_human_seal_required",
            "human_sealed=false",
        )
    try:
        load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    except UnknownRetrievalProfileError:
        return _print_block(
            "blocked=frozen_profile_and_human_seal_required",
            "human_sealed=true",
            "long_document_runtime=denied",
        )
    if args.split not in {"development", "qualification"}:
        return _print_block("blocked=unknown_split")
    return _run_split(args.split, labels, args.ids)


if __name__ == "__main__":
    raise SystemExit(main())
