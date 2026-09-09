"""Live Hybrid eval for the private PDF. Fails closed without ingest/seal."""

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
    retrieve_gates_pass,
)
from smart_rag_core.retrieval.frozen_profile import (
    FROZEN_HYBRID_PROFILE_SHA256,
    LONG_DOCUMENT_PROFILE_ID,
    UnknownRetrievalProfileError,
    load_frozen_profile,
    long_document_runtime_enabled,
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
    build_retrieve_report,
    candidate_digest,
    load_current_chunk_ids,
    print_retrieve_stdout,
    probe_infra,
    write_report,
)


def _print_block(*lines: str) -> int:
    """Print fail-closed tokens and return 2.

    Args:
        *lines: Safe stdout lines.

    Returns:
        Process exit code 2.
    """

    for line in lines:
        print(line)
    print("holdout_opened=false")
    print(f"content_class={ContentClass.REAL_COMPANY.value}")
    return 2


def _runtime_allow_listed() -> bool:
    """Return whether the long-document profile is frozen.

    Returns:
        True after Packet 16 freeze.
    """

    try:
        load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    except UnknownRetrievalProfileError:
        return False
    return True


def _run_split(
    *,
    split: str,
    labels: Path,
    ingest_ids: Path,
    live_rerank: bool,
) -> int:
    """Retrieve one open split with live full Hybrid.

    Args:
        split: ``development`` or ``qualification``.
        labels: Human-sealed gitignored JSON.
        ingest_ids: Captured ingest identity.
        live_rerank: Bind production rerank.

    Returns:
        ``0`` when aggregates were written, ``2`` on infrastructure miss.
        Does not open holdout.
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
    try:
        runtime = PdfEvalRuntime(
            supabase_url=supabase_url,
            parade_url=probed[1],
            settings=settings,
            version_id=version_id,
            current_chunk_ids=load_current_chunk_ids(supabase_url, version_id),
            live_rerank=live_rerank,
        )
        scores, _results = runtime.retrieve_labeled(
            labeled,
            default_profile_id=HYBRID_DEFAULT_PROFILE_ID,
            long_profile_id=LONG_DOCUMENT_PROFILE_ID,
        )
    except RuntimeError as error:
        return _print_block(f"blocked={error}")
    if not scores:
        return _print_block("blocked=no_scored_cases")
    report = build_retrieve_report(
        labeled,
        scores,
        candidate_profile_id=LONG_DOCUMENT_PROFILE_ID,
        runtime_allow_listed=_runtime_allow_listed(),
        live_rerank=live_rerank,
    )
    report["split"] = split
    report["default_profile_digest"] = FROZEN_HYBRID_PROFILE_SHA256
    out_name = (
        "hybrid-dev-report.json"
        if split == "development"
        else "hybrid-qual-report.json"
    )
    write_report(Path(".private-eval") / out_name, report)
    print_retrieve_stdout(report)
    print(f"gates_pass={retrieve_gates_pass(report)}")
    default = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    print(f"default_profile_id={default.profile_id}")
    if long_document_runtime_enabled():
        print("long_document_runtime=allow_listed")
    else:
        print("long_document_runtime=denied")
    return 0


def _freeze_if_ready() -> int:
    """Allow freeze only when development and qualification reports pass.

    Returns:
        ``0`` when both reports pass; ``2`` otherwise. Does not mutate
        the runtime allow-list itself.
    """

    dev = Path(".private-eval/hybrid-dev-report.json")
    qual = Path(".private-eval/hybrid-qual-report.json")
    if not dev.is_file() or not qual.is_file():
        return _print_block(
            "blocked=qualification_and_gates_required_before_freeze",
            "runtime_allow_listed=false",
        )
    development = json.loads(dev.read_text(encoding="utf-8"))
    qualification = json.loads(qual.read_text(encoding="utf-8"))
    if not retrieve_gates_pass(development) or not retrieve_gates_pass(qualification):
        return _print_block(
            "blocked=qualification_gates_failed",
            "runtime_allow_listed=false",
        )
    if (
        development.get("live_rerank") is not True
        or qualification.get("live_rerank") is not True
    ):
        return _print_block("blocked=identity_cannot_freeze_live_hybrid")
    digest = candidate_digest(LONG_DOCUMENT_PROFILE_ID)
    decision: dict[str, object] = {
        "freeze_ready": True,
        "candidate_profile_id": LONG_DOCUMENT_PROFILE_ID,
        "candidate_digest": digest,
        "default_profile_digest": FROZEN_HYBRID_PROFILE_SHA256,
        "holdout_opened": False,
        "rollback_profile_id": HYBRID_DEFAULT_PROFILE_ID,
    }
    write_report(Path(".private-eval/freeze-decision.json"), decision)
    print("freeze_ready=true")
    print(f"candidate_digest={digest}")
    print(f"default_profile_digest={FROZEN_HYBRID_PROFILE_SHA256}")
    print("holdout_opened=false")
    print("runtime_allow_listed=false")
    print("pin_long_document_sha256_in_frozen_profile_to_complete")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Refuse to tune or open holdout when live gates are missing.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``2`` until provider approval, ingest evidence, and a human seal exist.
        Qualification uses the evaluation candidate and does not freeze.
    """

    parser = argparse.ArgumentParser(
        description="Private PDF Hybrid eval. Holdout stays sealed."
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
    parser.add_argument(
        "--freeze",
        action="store_true",
        help="Succeeds only when development and qualification reports pass.",
    )
    parser.add_argument(
        "--rerank",
        choices=("live", "identity"),
        default="live",
        help="Main result requires live. Identity is a declared comparison.",
    )
    args = parser.parse_args(argv)
    env = apply_merged_env()
    if args.split == "holdout":
        return _print_block("blocked=holdout_sealed")
    try:
        assert_holdout_path_hidden(args.labels)
    except HoldoutSealedError:
        return _print_block("blocked=holdout_sealed")
    if not matrix_verified(env):
        return _print_block("blocked=provider_matrix_unverified")
    if args.freeze:
        return _freeze_if_ready()
    if not args.live:
        return _print_block("blocked=live_full_hybrid_required")
    try:
        require_live_models(env)
    except RuntimeError as error:
        return _print_block(f"blocked={error}")
    if not args.ids.is_file():
        return _print_block("blocked=ingest_and_human_seal_required")
    labels = resolve_labels_path(args.labels, args.ids)
    if not labels.is_file():
        return _print_block(
            "blocked=ingest_and_human_seal_required",
            "human_sealed=false",
        )
    cases = load_private_pdf_tuning_cases(labels)
    if not development_labels_are_sealed(cases):
        return _print_block(
            "blocked=ingest_and_human_seal_required",
            "human_sealed=false",
        )
    if args.split not in {"development", "qualification"}:
        return _print_block("blocked=unknown_split")
    live_rerank = args.rerank == "live"
    return _run_split(
        split=args.split,
        labels=labels,
        ingest_ids=args.ids,
        live_rerank=live_rerank,
    )


if __name__ == "__main__":
    raise SystemExit(main())
