"""One-time private PDF holdout runner. Default deny."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from uuid import UUID, uuid4

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.evaluation.private_pdf import (
    load_private_pdf_labeled_holdout,
    retrieve_gates_pass,
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
)
from scripts.pdf_eval_runtime import (  # noqa: E402
    PdfEvalRuntime,
    build_retrieve_report,
    generate_live_answer,
    judge_pdf_answer,
    load_current_chunk_ids,
    probe_infra,
    score_agent_rows,
    write_report,
)


def _git_sha() -> str:
    """Return HEAD SHA or unknown.

    Returns:
        Git SHA hex.
    """

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],  # noqa: S607
            cwd=REPO,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip()


def main(argv: list[str] | None = None) -> int:
    """Run one authorized holdout opening after freeze and qualification.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``2`` with ``holdout_opened=false`` until freeze and an immutable
        purpose token exist. Incomplete results are recorded failures,
        not rerun excuses.
    """

    parser = argparse.ArgumentParser(
        description="Private PDF holdout. Default deny. One authorized opening."
    )
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument(
        "--ids",
        type=Path,
        default=Path(".private-eval/ingest-ids.json"),
    )
    args = parser.parse_args(argv)
    env = apply_merged_env()
    print(f"content_class={ContentClass.REAL_COMPANY.value}")
    if not matrix_verified(env):
        print("blocked=provider_matrix_unverified")
        print("holdout_opened=false")
        return 2
    access = HoldoutAccess.from_settings()
    if not access.allowed:
        print("blocked=holdout_sealed")
        print("holdout_opened=false")
        return 2
    if access.purpose != "packet8_immutable_holdout":
        print("blocked=holdout_purpose_not_immutable_run")
        print("holdout_opened=false")
        return 2
    try:
        require_live_models(env)
    except RuntimeError as error:
        print(f"blocked={error}")
        print("holdout_opened=false")
        return 2
    try:
        load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    except UnknownRetrievalProfileError:
        print("blocked=holdout_requires_frozen_qualification")
        print("holdout_opened=false")
        return 2
    if not args.ids.is_file():
        print("blocked=ingest_identity_missing")
        print("holdout_opened=false")
        return 2
    labeled = load_private_pdf_labeled_holdout(args.labels, holdout_access=access)
    if not labeled:
        print("blocked=holdout_labels_empty")
        print("holdout_opened=false")
        return 2
    ids = json.loads(args.ids.read_text(encoding="utf-8"))
    version_id = UUID(str(ids["version_id"]))
    settings = SharedSettings()
    supabase_url = operator_url(env)
    probed = probe_infra(supabase_url)
    if probed is None:
        print("blocked=supabase_or_paradedb_unavailable")
        print("holdout_opened=false")
        return 2
    run_id = str(uuid4())
    print("holdout_opened=true")
    print(f"holdout_run_id={run_id}")
    print(f"holdout_actor={access.actor}")
    print(f"holdout_purpose={access.purpose}")
    print(f"git_sha={_git_sha()}")
    runtime = PdfEvalRuntime(
        supabase_url=supabase_url,
        parade_url=probed[1],
        settings=settings,
        version_id=version_id,
        current_chunk_ids=load_current_chunk_ids(supabase_url, version_id),
        live_rerank=True,
    )
    scores, results = runtime.retrieve_labeled(
        labeled,
        default_profile_id=HYBRID_DEFAULT_PROFILE_ID,
        long_profile_id=LONG_DOCUMENT_PROFILE_ID,
    )
    retrieve_report = build_retrieve_report(
        labeled,
        scores,
        candidate_profile_id=LONG_DOCUMENT_PROFILE_ID,
        runtime_allow_listed=True,
        live_rerank=True,
    )
    retrieve_report["holdout_opened"] = True
    retrieve_report["holdout_run_id"] = run_id
    answers: list[AnswerPayload] = []
    judges: list[tuple[str, float | None]] = []
    incomplete = 0
    for row, result in zip(labeled, results, strict=True):
        if str(result.fallback_reason) != "none":
            incomplete += 1
        answer = generate_live_answer(
            settings=settings,
            query=row.question,
            result=result,
        )
        excerpts = tuple(unit.citation_text[:800] for unit in result.evidence[:8])
        judges.append(
            judge_pdf_answer(
                query=row.question,
                answer_text=answer.answer_text,
                atomic_facts=row.atomic_facts,
                excerpt_ids=tuple(str(unit.chunk_id) for unit in result.evidence),
                excerpts=excerpts,
            )
        )
        answers.append(answer)
    agent_report = score_agent_rows(labeled, results, answers, judges)
    agent_report["holdout_opened"] = True
    combined = {
        "holdout_opened": True,
        "holdout_run_id": run_id,
        "holdout_actor": access.actor,
        "holdout_purpose": access.purpose,
        "git_sha": _git_sha(),
        "incomplete_count": incomplete,
        "retrieve": retrieve_report,
        "agent": agent_report,
        "retrieve_gates_pass": retrieve_gates_pass(retrieve_report),
        "agent_gates_pass": agent_report.get("agent_gates_pass"),
        "no_go": incomplete > 0
        or not retrieve_gates_pass(retrieve_report)
        or not bool(agent_report.get("agent_gates_pass")),
    }
    write_report(Path(".private-eval/holdout-report.json"), combined)
    print(f"case_count={retrieve_report['case_count']}")
    print(f"hybrid_recall_at_10={retrieve_report['hybrid_recall_at_10']}")
    print(f"incomplete_count={incomplete}")
    print(f"no_go={combined['no_go']}")
    return 2 if combined["no_go"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
