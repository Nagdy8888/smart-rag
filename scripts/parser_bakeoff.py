#!/usr/bin/env python3
"""Operator CLI for the isolated PDF parser bake-off.

Never prints source text, questions, answers, excerpts, or credentials.
``--force`` cannot bypass label seals, provider-matrix gates, ACL checks, or
holdout denial.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

from smart_rag_core.evaluation.parser_bakeoff.artifacts import (
    canonical_json,
    lane_dir,
    load_manifest,
    read_model,
    repo_root_from,
    run_dir,
    save_manifest,
    sha256_text,
    write_json_atomic,
)
from smart_rag_core.evaluation.parser_bakeoff.cleanup import cleanup_run
from smart_rag_core.evaluation.parser_bakeoff.constants import (
    AGENT_REPORT_NAME,
    ANYDOC_LANE,
    CLEANUP_RECEIPT_NAME,
    COMPARISON_JSON_NAME,
    COMPARISON_MD_NAME,
    CURRENT_LANE,
    FORBIDDEN_SPLIT,
    LANE_IDS,
    NEUTRAL_CASES_NAME,
    RETRIEVAL_REPORT_NAME,
    SELECTED_PDF_RELATIVE,
    LaneId,
)
from smart_rag_core.evaluation.parser_bakeoff.evaluate import (
    alternate_lane_order,
    assert_version_scoped,
    labeled_for_lane,
    score_agent,
    score_retrieve,
)
from smart_rag_core.evaluation.parser_bakeoff.indexing import persist_lane_index
from smart_rag_core.evaluation.parser_bakeoff.mapping import (
    assert_allowed_split,
    review_pending_count,
    to_neutral_cases,
)
from smart_rag_core.evaluation.parser_bakeoff.metrics import compare_reports
from smart_rag_core.evaluation.parser_bakeoff.models import (
    BakeoffError,
    BakeoffManifest,
    ChunkSummary,
    GoldMap,
    LaneAgentScore,
    LaneIngestIds,
    LaneRetrieveScore,
    NeutralCase,
    NeutralCaseSet,
    RunStage,
)
from smart_rag_core.evaluation.parser_bakeoff.pipeline import (
    CURRENT_AND_ANYDOC,
    identity_for,
    load_chunk_summary,
    load_gold_map,
    load_ingest_ids,
    load_parse_result,
    map_lane_gold,
    parse_lane_artifacts,
    require_stage,
    update_manifest_lanes,
    validate_lane_gold,
)
from smart_rag_core.evaluation.parser_bakeoff.preflight import (
    prepare_run,
    selected_pdf_path,
    stream_sha256,
)
from smart_rag_core.evaluation.parser_bakeoff.report import render_markdown
from smart_rag_core.evaluation.private_pdf import (
    development_labels_are_sealed,
    load_private_pdf_labeled_qualification,
    load_private_pdf_labeled_tuning,
)
from smart_rag_core.ingestion.embeddings.policy import EMBEDDING_MODEL
from smart_rag_core.ingestion.parser.types import ParseDisposition
from smart_rag_core.retrieval.coverage import CoverageDecision
from smart_rag_core.retrieval.hybrid_run import HybridRunResult
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.security.external_processing import ContentClass
from smart_rag_core.settings import SharedSettings, get_process_environ

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
    candidate_digest,
    generate_live_answer,
    judge_pdf_answer,
    load_current_chunk_ids,
    probe_infra,
)


def _print_block(*lines: str) -> int:
    """Print fail-closed tokens.

    Args:
        *lines: Safe stdout lines.

    Returns:
        Exit code 2.
    """

    for line in lines:
        print(line)
    print("holdout_opened=false")
    print(f"content_class={ContentClass.REAL_COMPANY.value}")
    print("generalization_claim=false")
    return 2


def _parse_lanes(raw: str) -> tuple[LaneId, ...]:
    """Parse a comma-separated lane list.

    Args:
        raw: CLI lane string.

    Returns:
        Ordered unique lanes.

    Raises:
        BakeoffError: When a lane is unknown.
    """

    seen: list[LaneId] = []
    for item in raw.split(","):
        token = item.strip()
        if token not in LANE_IDS:
            raise BakeoffError("unknown_lane", "unsupported lane")
        if token not in seen:
            seen.append(token)  # type: ignore[arg-type]
    return tuple(seen) or CURRENT_AND_ANYDOC


def _source_bytes(repo: Path, manifest: BakeoffManifest) -> bytes:
    """Read the selected PDF and confirm the manifest hash.

    Args:
        repo: Repository root.
        manifest: Run manifest.

    Returns:
        Exact PDF bytes.

    Raises:
        BakeoffError: When the file changed.
    """

    path = selected_pdf_path(repo)
    digest, size = stream_sha256(path)
    if digest != manifest.source_sha256 or size != manifest.source_bytes:
        raise BakeoffError(
            "hash_mismatch", "selected PDF no longer matches the manifest"
        )
    payload = path.read_bytes()
    if len(payload) != size:
        raise BakeoffError("hash_mismatch", "selected PDF changed during read")
    return payload


def _cmd_prepare(args: argparse.Namespace) -> int:
    """Create a private run directory and manifest.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        manifest = prepare_run(repo=repo, pdf=Path(args.pdf))
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    print(f"run_id={manifest.run_id}")
    print(f"source_sha256={manifest.source_sha256}")
    print(f"source_pages={manifest.source_pages}")
    print(f"stage={manifest.stage.value}")
    print("holdout_opened=false")
    print("generalization_claim=false")
    return 0


def _cmd_parse(args: argparse.Namespace) -> int:
    """Parse selected lanes sequentially.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        env = apply_merged_env()
        if env.get("LANGSMITH_EXPORT_IO", "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            raise BakeoffError(
                "langsmith_export_io", "LANGSMITH_EXPORT_IO must be false"
            )
        lanes = _parse_lanes(args.lanes)
        if ANYDOC_LANE in lanes and not matrix_verified(env):
            raise BakeoffError(
                "provider_matrix_unverified", "provider matrix is not verified"
            )
        manifest = load_manifest(repo, args.run_id)
        payload = _source_bytes(repo, manifest)
        ingest: dict[LaneId, LaneIngestIds] = {}
        summaries: dict[LaneId, ChunkSummary] = {}
        for lane_id in lanes:
            _result, summary, ids = parse_lane_artifacts(
                repo,
                manifest,
                payload=payload,
                lane_id=lane_id,
                use_docker=not args.inprocess,
                resume=args.resume,
            )
            ingest[lane_id] = ids
            summaries[lane_id] = summary
            print(
                f"lane={lane_id} disposition={summary.disposition} "
                f"chunks={summary.chunk_count} extracted_chars={summary.extracted_chars} "
                f"ocr_pages={summary.ocr_pages} replay_matched={summary.replay_matched}"
            )
            if summary.failure_code:
                print(f"lane={lane_id} failure_code={summary.failure_code}")
        update_manifest_lanes(repo, manifest, ingest, summaries, stage=RunStage.PARSED)
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    print(f"run_id={args.run_id}")
    print("holdout_opened=false")
    return 0


def _live_settings() -> tuple[dict[str, str], SharedSettings, str, str]:
    """Load merged env, require live models, and resolve store URLs.

    Returns:
        Environment mapping, settings, Supabase URL, ParadeDB URL.

    Raises:
        BakeoffError: When gates fail.
    """

    env = apply_merged_env()
    if not matrix_verified(env):
        raise BakeoffError(
            "provider_matrix_unverified", "provider matrix is not verified"
        )
    if env.get("LANGSMITH_EXPORT_IO", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        raise BakeoffError("langsmith_export_io", "LANGSMITH_EXPORT_IO must be false")
    try:
        require_live_models(env)
        settings = SharedSettings()
    except (RuntimeError, ValueError) as exc:
        raise BakeoffError(
            "openai_required", "live OpenAI settings are required"
        ) from exc
    if settings.mock_model_mode:
        raise BakeoffError("mock_model_mode", "MOCK_MODEL_MODE must be false")
    try:
        supabase_url = operator_url(env)
    except RuntimeError as exc:
        raise BakeoffError(
            "operator_url_missing", "OPERATOR_SUPABASE_DB_URL is required"
        ) from exc
    parade_url = (
        get_process_environ("PARADEDB_URL") or env.get("PARADEDB_URL") or ""
    ).strip()
    if not parade_url:
        raise BakeoffError("paradedb_url_missing", "PARADEDB_URL is required")
    return env, settings, supabase_url, parade_url


def _score_live_answer_or_unscored(
    case: NeutralCase,
    mapping: GoldMap,
    *,
    settings: SharedSettings,
    question: str,
    atomic_facts: Sequence[str],
    result: HybridRunResult,
) -> LaneAgentScore:
    """Generate and judge one answer, or record an unscored bound failure.

    Args:
        case: Neutral case. Question text is not printed.
        mapping: Approved gold map for this lane.
        settings: Live model settings.
        question: Case question. Never logged.
        atomic_facts: Approved facts. Never logged.
        result: Version-scoped Hybrid result.

    Returns:
        Per-case agent score. Gateway input-bound and timeout failures are
        ``unscored`` and never treated as a pass. The OpenAI 16384-character
        limit is not raised.
    """

    try:
        answer = generate_live_answer(settings=settings, query=question, result=result)
    except (TimeoutError, ValueError):
        return score_agent(
            case,
            mapping,
            cited_ids=(),
            judge_status="unscored",
            faithfulness=None,
            refused=False,
            answer_calls=1,
            judge_calls=0,
            input_tokens=0,
            output_tokens=0,
            cost_usd=None,
            budget_failed=True,
        )
    excerpts = tuple(unit.citation_text[:500] for unit in result.evidence[:12])
    excerpt_ids = tuple(str(unit.chunk_id) for unit in result.evidence[:12])
    judge_status, faith = judge_pdf_answer(
        query=question,
        answer_text=answer.answer_text,
        atomic_facts=atomic_facts,
        excerpt_ids=excerpt_ids,
        excerpts=excerpts,
    )
    cited: list[UUID] = []
    for citation in answer.citations:
        if citation.chunk_id:
            cited.append(UUID(str(citation.chunk_id)))
    refused = answer.status == "refused" or (
        result.coverage.decision is CoverageDecision.REFUSE
    )
    return score_agent(
        case,
        mapping,
        cited_ids=cited,
        judge_status=judge_status,
        faithfulness=faith,
        refused=refused,
        answer_calls=1,
        judge_calls=1,
        input_tokens=0,
        output_tokens=0,
        cost_usd=None,
        budget_failed=False,
    )


def _cmd_index(args: argparse.Namespace) -> int:
    """Index successful lanes as restricted graph-ineligible versions.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        manifest = load_manifest(repo, args.run_id)
        require_stage(manifest, RunStage.PARSED)
        _env, settings, supabase_url, parade_url = _live_settings()
        actor = UUID(str(args.actor_id or manifest.actor_id))
        ingest_map: dict[LaneId, LaneIngestIds] = {}
        summaries: dict[LaneId, ChunkSummary] = {}
        import psycopg

        with (
            psycopg.connect(supabase_url) as supabase,
            psycopg.connect(parade_url, connect_timeout=8) as parade,
        ):
            for lane_id in CURRENT_AND_ANYDOC:
                parse_result = load_parse_result(repo, manifest.run_id, lane_id)
                allocated = load_ingest_ids(repo, manifest.run_id, lane_id)
                if parse_result.disposition is ParseDisposition.FAILED:
                    print(f"lane={lane_id} skipped=parse_failed")
                    ingest_map[lane_id] = allocated
                    continue
                supabase.execute("SET ROLE postgres")
                existing = supabase.execute(
                    """
                    SELECT status::text, is_current
                    FROM app.document_versions
                    WHERE id = %s
                      AND deleted_at IS NULL
                    """,
                    (allocated.version_id,),
                ).fetchone()
                status = str(existing[0]) if existing is not None else ""
                is_current = bool(existing[1]) if existing is not None else False
                already_indexed = status == "hybrid_ready" or status == "graph_pending"
                if status == "graph_ineligible" and is_current:
                    already_indexed = True
                if already_indexed:
                    stamped = allocated.model_copy(
                        update={"status": status, "hybrid_ready": True}
                    )
                    write_json_atomic(
                        lane_dir(repo, manifest.run_id, lane_id) / "ingest-ids.json",
                        stamped,
                    )
                    print(f"lane={lane_id} skipped=already_indexed")
                    ingest_map[lane_id] = stamped
                    summaries[lane_id] = load_chunk_summary(
                        repo, manifest.run_id, lane_id
                    )
                    continue
                written = persist_lane_index(
                    supabase,
                    parade,
                    parse_result=parse_result,
                    run_id=manifest.run_id,
                    lane_id=lane_id,
                    filename=manifest.source_basename,
                    source_sha256=manifest.source_sha256,
                    scan=manifest.scan,
                    actor_id=actor,
                    settings=settings,
                    document_id=allocated.document_id,
                    version_id=allocated.version_id,
                )
                write_json_atomic(
                    lane_dir(repo, manifest.run_id, lane_id) / "ingest-ids.json",
                    written,
                )
                ingest_map[lane_id] = written
                summaries[lane_id] = load_chunk_summary(repo, manifest.run_id, lane_id)
                print(
                    f"lane={lane_id} status={written.status} "
                    f"hybrid_ready={written.hybrid_ready} chunks={written.chunk_count}"
                )
        stamped = update_manifest_lanes(
            repo,
            manifest.model_copy(
                update={
                    "actor_id": str(actor),
                    "embedding_model": EMBEDDING_MODEL,
                    "chat_model": settings.openai_chat_model_id,
                    "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
                }
            ),
            ingest_map,
            summaries,
            stage=RunStage.INDEXED,
        )
        print(f"run_id={stamped.run_id}")
        print(f"embedding_model={stamped.embedding_model}")
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    except ValueError:
        return _print_block("blocked=actor_id_required")
    print("holdout_opened=false")
    return 0


def _load_labeled(repo: Path, manifest: BakeoffManifest, split: str, labels: Path):
    """Load sealed open-split labeled cases.

    Args:
        repo: Repository root.
        manifest: Run manifest.
        split: Requested split.
        labels: Caller labels path.

    Returns:
        Labeled cases.

    Raises:
        BakeoffError: On holdout, missing, or unsealed labels.
    """

    assert_allowed_split(split, protocol_frozen=manifest.protocol_frozen)
    ingest_hint = repo / ".private-eval" / "ingest-ids.json"
    resolved = resolve_labels_path(labels, ingest_hint)
    digest_path = (
        repo / ".private-eval" / manifest.source_sha256[:12] / "v1" / "sealed.json"
    )
    if digest_path.is_file():
        resolved = digest_path
    if not resolved.is_file():
        raise BakeoffError("labels_missing", "sealed open-split labels are missing")
    if split == "qualification":
        cases = load_private_pdf_labeled_qualification(resolved)
    else:
        cases = load_private_pdf_labeled_tuning(resolved)
    if not cases:
        raise BakeoffError("no_scored_cases", "no open-split cases")
    if (
        not development_labels_are_sealed(tuple(item.meta for item in cases))
        and split == "development"
    ):
        raise BakeoffError("human_sealed_false", "development labels are not sealed")
    return cases, resolved


def _cmd_map_gold(args: argparse.Namespace) -> int:
    """Derive parser-neutral cases and map facts per lane.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        if args.split == FORBIDDEN_SPLIT:
            raise BakeoffError("holdout_sealed", "holdout split is forbidden")
        manifest = load_manifest(repo, args.run_id)
        require_stage(manifest, RunStage.INDEXED)
        labeled, resolved = _load_labeled(repo, manifest, args.split, Path(args.labels))
        seal_hash = sha256_text(resolved.read_text(encoding="utf-8"))
        neutral = to_neutral_cases(
            labeled,
            source_sha256=manifest.source_sha256,
            original_seal_sha256=seal_hash,
            split=args.split,
        )
        write_json_atomic(run_dir(repo, manifest.run_id) / NEUTRAL_CASES_NAME, neutral)
        pending_total = 0
        for lane_id in CURRENT_AND_ANYDOC:
            mapping = map_lane_gold(repo, manifest, neutral, lane_id)
            pending = review_pending_count(mapping)
            pending_total += pending
            print(
                f"lane={lane_id} gold_items={len(mapping.items)} review_pending={pending}"
            )
        save_manifest(repo, manifest.model_copy(update={"stage": RunStage.MAPPED}))
        print(f"run_id={manifest.run_id}")
        print(f"neutral_cases={len(neutral.cases)}")
        print(f"mapping_review_count={pending_total}")
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    print("holdout_opened=false")
    return 0


def _load_decisions(
    path: Path | None,
) -> tuple[
    dict[tuple[str, int], tuple[UUID, ...]],
    set[tuple[str, int]],
]:
    """Load optional human review decisions.

    Args:
        path: JSON decisions file.

    Returns:
        Decisions and rejected keys.
    """

    if path is None or not path.is_file():
        return {}, set()
    raw = json.loads(path.read_text(encoding="utf-8"))
    decisions: dict[tuple[str, int], tuple[UUID, ...]] = {}
    for item in raw.get("decisions", []):
        key = (str(item["case_id"]), int(item["fact_index"]))
        decisions[key] = tuple(UUID(str(value)) for value in item.get("chunk_ids", []))
    rejected = {
        (str(item["case_id"]), int(item["fact_index"]))
        for item in raw.get("rejected", [])
    }
    return decisions, rejected


def _cmd_validate_gold(args: argparse.Namespace) -> int:
    """Approve gold maps after review.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        manifest = load_manifest(repo, args.run_id)
        require_stage(manifest, RunStage.MAPPED)
        decisions, rejected = _load_decisions(
            Path(args.decisions) if args.decisions else None
        )
        for lane_id in CURRENT_AND_ANYDOC:
            approved = validate_lane_gold(
                repo,
                manifest.run_id,
                lane_id,
                reviewer=args.reviewer,
                decisions=decisions,
                rejected=rejected,
            )
            print(
                f"lane={lane_id} approved={approved.approved} "
                f"reviewer={approved.reviewer} items={len(approved.items)}"
            )
        save_manifest(
            repo, manifest.model_copy(update={"stage": RunStage.GOLD_VALIDATED})
        )
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    print(f"run_id={args.run_id}")
    print("holdout_opened=false")
    return 0


def _cmd_evaluate(args: argparse.Namespace) -> int:
    """Run paired version-scoped retrieval and answer evaluation.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        if args.split == FORBIDDEN_SPLIT:
            raise BakeoffError("holdout_sealed", "holdout split is forbidden")
        manifest = load_manifest(repo, args.run_id)
        require_stage(manifest, RunStage.GOLD_VALIDATED)
        if not args.live:
            raise BakeoffError("live_required", "evaluate requires --live")
        env, settings, supabase_url, parade_url = _live_settings()
        probe = probe_infra(supabase_url)
        if probe is None:
            raise BakeoffError("infra_missing", "Supabase or ParadeDB probe failed")
        cases = read_model(
            run_dir(repo, manifest.run_id) / NEUTRAL_CASES_NAME, NeutralCaseSet
        )
        if cases.split != args.split:
            raise BakeoffError("split_mismatch", "neutral cases split does not match")
        maps = {
            CURRENT_LANE: load_gold_map(repo, manifest.run_id, CURRENT_LANE),
            ANYDOC_LANE: load_gold_map(repo, manifest.run_id, ANYDOC_LANE),
        }
        ingest = {
            CURRENT_LANE: load_ingest_ids(repo, manifest.run_id, CURRENT_LANE),
            ANYDOC_LANE: load_ingest_ids(repo, manifest.run_id, ANYDOC_LANE),
        }
        for _lane_id, mapping in maps.items():
            if not mapping.approved:
                raise BakeoffError("gold_unapproved", "gold map is not approved")
        chunk_ids = {
            lane_id: load_current_chunk_ids(supabase_url, ingest[lane_id].version_id)
            for lane_id in CURRENT_AND_ANYDOC
        }
        retrieve_scores: dict[str, list[LaneRetrieveScore]] = {
            CURRENT_LANE: [],
            ANYDOC_LANE: [],
        }
        agent_scores: dict[str, list[LaneAgentScore]] = {
            CURRENT_LANE: [],
            ANYDOC_LANE: [],
        }
        runtimes = {
            lane_id: PdfEvalRuntime(
                supabase_url=supabase_url,
                parade_url=parade_url,
                settings=settings,
                version_id=ingest[lane_id].version_id,
                current_chunk_ids=chunk_ids[lane_id],
                live_rerank=True,
            )
            for lane_id in CURRENT_AND_ANYDOC
        }
        labeled = {
            lane_id: labeled_for_lane(cases.cases, maps[lane_id])
            for lane_id in CURRENT_AND_ANYDOC
        }
        for index, case in enumerate(cases.cases):
            for lane_id in alternate_lane_order(index):
                print(
                    f"case_index={index} lane={lane_id} cases={len(cases.cases)}",
                    flush=True,
                )
                row = labeled[lane_id][index]
                scores, results = runtimes[lane_id].retrieve_labeled(
                    (row,),
                    default_profile_id=HYBRID_DEFAULT_PROFILE_ID,
                    long_profile_id=row.meta.expected_profile_id,
                )
                del scores
                result = results[0]
                foreign = (
                    chunk_ids[ANYDOC_LANE]
                    if lane_id == CURRENT_LANE
                    else chunk_ids[CURRENT_LANE]
                )
                leaks = assert_version_scoped(
                    result,
                    allowed_chunk_ids=chunk_ids[lane_id],
                    version_id=ingest[lane_id].version_id,
                    foreign_chunk_ids=foreign,
                )
                acl_leak = any(
                    chunk_id not in chunk_ids[lane_id] for chunk_id in result.ranked_ids
                )
                retrieve_scores[lane_id].append(
                    score_retrieve(
                        case,
                        result,
                        gold_ids=row.meta.chunk_ids,
                        locator_available=identity_for(
                            manifest, lane_id
                        ).locator_available,
                        cross_lane_leaks=leaks,
                        acl_leak=acl_leak,
                    )
                )
                agent_scores[lane_id].append(
                    _score_live_answer_or_unscored(
                        case,
                        maps[lane_id],
                        settings=settings,
                        question=row.question,
                        atomic_facts=row.atomic_facts,
                        result=result,
                    )
                )
        for lane_id in CURRENT_AND_ANYDOC:
            retrieval_path = (
                lane_dir(repo, manifest.run_id, lane_id) / RETRIEVAL_REPORT_NAME
            )
            agent_path = lane_dir(repo, manifest.run_id, lane_id) / AGENT_REPORT_NAME
            write_json_atomic(
                retrieval_path,
                {
                    "lane_id": lane_id,
                    "scores": [
                        item.model_dump(mode="json")
                        for item in retrieve_scores[lane_id]
                    ],
                },
            )
            write_json_atomic(
                agent_path,
                {
                    "lane_id": lane_id,
                    "scores": [
                        item.model_dump(mode="json") for item in agent_scores[lane_id]
                    ],
                },
            )
        digest = candidate_digest(HYBRID_DEFAULT_PROFILE_ID)
        save_manifest(
            repo,
            manifest.model_copy(
                update={
                    "stage": RunStage.EVALUATED,
                    "retrieval_profile_id": HYBRID_DEFAULT_PROFILE_ID,
                    "retrieval_profile_digest": digest,
                    "experimental_only": True,
                }
            ),
        )
        bound_failures = sum(
            1
            for lane_id in CURRENT_AND_ANYDOC
            for item in agent_scores[lane_id]
            if item.budget_or_deadline_failed
        )
        print(f"run_id={manifest.run_id}")
        print(f"cases={len(cases.cases)}")
        print(f"answer_bound_failures={bound_failures}")
        print("live=true")
        del env
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    print("holdout_opened=false")
    print("generalization_claim=false")
    return 0


def _load_lane_scores(
    repo: Path, run_id: str, lane_id: LaneId
) -> tuple[tuple[LaneRetrieveScore, ...], tuple[LaneAgentScore, ...]]:
    """Load stored per-lane scores.

    Args:
        repo: Repository root.
        run_id: Run identifier.
        lane_id: Lane token.

    Returns:
        Retrieval and agent scores.
    """

    retrieval_raw = json.loads(
        (lane_dir(repo, run_id, lane_id) / RETRIEVAL_REPORT_NAME).read_text(
            encoding="utf-8"
        )
    )
    agent_raw = json.loads(
        (lane_dir(repo, run_id, lane_id) / AGENT_REPORT_NAME).read_text(
            encoding="utf-8"
        )
    )
    retrieve = tuple(
        LaneRetrieveScore.model_validate(item)
        for item in retrieval_raw.get("scores", [])
    )
    agent = tuple(
        LaneAgentScore.model_validate(item) for item in agent_raw.get("scores", [])
    )
    return retrieve, agent


def _cmd_report(args: argparse.Namespace) -> int:
    """Write private JSON and Markdown comparison reports.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        manifest = load_manifest(repo, args.run_id)
        require_stage(manifest, RunStage.EVALUATED)
        current_r, current_a = _load_lane_scores(repo, manifest.run_id, CURRENT_LANE)
        anydoc_r, anydoc_a = _load_lane_scores(repo, manifest.run_id, ANYDOC_LANE)
        current_map = load_gold_map(repo, manifest.run_id, CURRENT_LANE)
        anydoc_map = load_gold_map(repo, manifest.run_id, ANYDOC_LANE)
        review_count = review_pending_count(current_map) + review_pending_count(
            anydoc_map
        )
        report = compare_reports(
            run_id=manifest.run_id,
            source_sha256=manifest.source_sha256,
            source_basename=manifest.source_basename,
            current_identity=identity_for(manifest, CURRENT_LANE),
            anydoc_identity=identity_for(manifest, ANYDOC_LANE),
            current_chunk=load_chunk_summary(repo, manifest.run_id, CURRENT_LANE),
            anydoc_chunk=load_chunk_summary(repo, manifest.run_id, ANYDOC_LANE),
            current_retrieve=current_r,
            anydoc_retrieve=anydoc_r,
            current_agent=current_a,
            anydoc_agent=anydoc_a,
            mapping_review_count=review_count,
            infra_mismatch=False,
        )
        folder = run_dir(repo, manifest.run_id)
        json_path = folder / COMPARISON_JSON_NAME
        md_path = folder / COMPARISON_MD_NAME
        write_json_atomic(json_path, report)
        markdown = render_markdown(report)
        json_digest = sha256_text(canonical_json(report.model_dump(mode="json")))
        markdown += f"- report_json_sha256: `{json_digest}`\n"
        md_path.write_text(markdown, encoding="utf-8")
        save_manifest(repo, manifest.model_copy(update={"stage": RunStage.REPORTED}))
        metrics = {item.name: item for item in report.paired_metrics}
        recall = metrics["hybrid_recall_at_10"]
        citation = metrics["citation_correctness"]
        faith = metrics["judge_faithfulness"]
        print(f"run_id={report.run_id}")
        print(f"source_sha256={report.source_sha256}")
        print("scope=single_document_experiment")
        print(f"current_recall_at_10={recall.current}")
        print(f"anydoc_local_recall_at_10={recall.anydoc_local}")
        print(f"delta_recall_at_10_pp={recall.delta}")
        print(f"current_citation_correctness={citation.current}")
        print(f"anydoc_local_citation_correctness={citation.anydoc_local}")
        print(f"current_faithfulness={faith.current}")
        print(f"anydoc_local_faithfulness={faith.anydoc_local}")
        print(
            f"current_locator_available={str(report.current.locator_available).lower()}"
        )
        print(
            f"anydoc_local_locator_available={str(report.anydoc_local.locator_available).lower()}"
        )
        print(f"classification={report.classification.value}")
        print("generalization_claim=false")
        print("holdout_opened=false")
        print(f"report_json={json_path}")
        print(f"report_markdown={md_path}")
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    return 0


def _cmd_cleanup(args: argparse.Namespace) -> int:
    """Delete only manifest-listed experiment rows.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    try:
        manifest = load_manifest(repo, args.run_id)
        lanes = tuple(
            load_ingest_ids(repo, manifest.run_id, lane_id)
            for lane_id in CURRENT_AND_ANYDOC
        )
        _env, _settings, supabase_url, parade_url = _live_settings()
        import psycopg

        with (
            psycopg.connect(supabase_url) as supabase,
            psycopg.connect(parade_url, connect_timeout=8) as parade,
        ):
            receipt = cleanup_run(
                supabase,
                parade,
                repo=repo,
                manifest=manifest,
                lanes=lanes,
                manifest_sha256=args.manifest_sha256,
                delete_private_reports=args.delete_private_reports,
            )
        write_json_atomic(
            run_dir(repo, manifest.run_id) / CLEANUP_RECEIPT_NAME, receipt
        )
        print(f"run_id={receipt.run_id}")
        print(f"documents_deleted={receipt.documents_deleted}")
        print(f"versions_deleted={receipt.versions_deleted}")
        print(f"chunks_remaining={receipt.chunks_remaining}")
        print(f"bm25_rows_remaining={receipt.bm25_rows_remaining}")
        print(f"reports_deleted={receipt.reports_deleted}")
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Resume completed stages then continue.

    Args:
        args: Parsed CLI args.

    Returns:
        Process exit code.
    """

    repo = repo_root_from(REPO)
    if args.split == FORBIDDEN_SPLIT:
        return _print_block("blocked=holdout_sealed")
    try:
        if not args.run_id:
            manifest = prepare_run(repo=repo, pdf=Path(args.pdf))
            print(f"run_id={manifest.run_id}")
            args.run_id = manifest.run_id
        manifest = load_manifest(repo, args.run_id)
    except BakeoffError as exc:
        return _print_block(f"blocked={exc.code}")
    commands: list[tuple[RunStage, Callable[[], int]]] = [
        (RunStage.PARSED, lambda: _cmd_parse(args)),
        (RunStage.INDEXED, lambda: _cmd_index(args)),
        (RunStage.MAPPED, lambda: _cmd_map_gold(args)),
        (RunStage.GOLD_VALIDATED, lambda: _cmd_validate_gold(args)),
        (RunStage.EVALUATED, lambda: _cmd_evaluate(args)),
        (RunStage.REPORTED, lambda: _cmd_report(args)),
    ]
    order = (
        RunStage.PREPARED,
        RunStage.PARSED,
        RunStage.INDEXED,
        RunStage.MAPPED,
        RunStage.GOLD_VALIDATED,
        RunStage.EVALUATED,
        RunStage.REPORTED,
    )
    current = order.index(manifest.stage)
    for stage, fn in commands:
        if args.resume and order.index(stage) <= current:
            continue
        code = fn()
        if code != 0:
            return code
        current = order.index(stage)
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the bake-off CLI parser.

    Returns:
        Argument parser.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Hash, bound, and scan the selected PDF")
    prepare.add_argument("--pdf", required=True, help="Path to the selected book PDF")
    prepare.set_defaults(func=_cmd_prepare)

    parse = sub.add_parser("parse", help="Parse lanes sequentially")
    parse.add_argument("--run-id", required=True)
    parse.add_argument("--lanes", default="current,anydoc_local")
    parse.add_argument("--resume", action="store_true")
    parse.add_argument(
        "--inprocess",
        action="store_true",
        help="Test-only in-process parsers. Live bake-off must use Docker.",
    )
    parse.set_defaults(func=_cmd_parse)

    index = sub.add_parser("index", help="Index isolated restricted versions")
    index.add_argument("--run-id", required=True)
    index.add_argument("--actor-id", default=None)
    index.add_argument("--force", action="store_true")
    index.set_defaults(func=_cmd_index)

    mapped = sub.add_parser("map-gold", help="Derive neutral cases and map gold")
    mapped.add_argument("--run-id", required=True)
    mapped.add_argument("--split", default="development")
    mapped.add_argument(
        "--labels",
        default=".private-eval/eval-draft/sealed.json",
    )
    mapped.add_argument("--force", action="store_true")
    mapped.set_defaults(func=_cmd_map_gold)

    validate = sub.add_parser("validate-gold", help="Approve gold maps")
    validate.add_argument("--run-id", required=True)
    validate.add_argument("--reviewer", required=True)
    validate.add_argument("--decisions", default=None)
    validate.add_argument("--force", action="store_true")
    validate.set_defaults(func=_cmd_validate_gold)

    evaluate = sub.add_parser("evaluate", help="Paired live retrieval and answer eval")
    evaluate.add_argument("--run-id", required=True)
    evaluate.add_argument("--split", default="development")
    evaluate.add_argument("--live", action="store_true")
    evaluate.add_argument("--resume", action="store_true")
    evaluate.add_argument("--force", action="store_true")
    evaluate.set_defaults(func=_cmd_evaluate)

    report = sub.add_parser("report", help="Write private comparison reports")
    report.add_argument("--run-id", required=True)
    report.set_defaults(func=_cmd_report)

    cleanup = sub.add_parser("cleanup", help="Delete manifest-listed experiment rows")
    cleanup.add_argument("--run-id", required=True)
    cleanup.add_argument("--manifest-sha256", required=True)
    cleanup.add_argument("--delete-private-reports", action="store_true")
    cleanup.add_argument("--force", action="store_true")
    cleanup.set_defaults(func=_cmd_cleanup)

    run = sub.add_parser("run", help="Resume completed stages")
    run.add_argument("--pdf", default=SELECTED_PDF_RELATIVE)
    run.add_argument("--run-id", default=None)
    run.add_argument("--lanes", default="current,anydoc_local")
    run.add_argument("--split", default="development")
    run.add_argument("--live", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--reviewer", default="Nagdy")
    run.add_argument("--actor-id", default=None)
    run.add_argument("--labels", default=".private-eval/eval-draft/sealed.json")
    run.add_argument("--decisions", default=None)
    run.add_argument("--inprocess", action="store_true")
    run.add_argument("--force", action="store_true")
    run.set_defaults(func=_cmd_run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point.

    Args:
        argv: Optional argument vector.

    Returns:
        Process exit code.
    """

    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, "force", False):
        print("force_ignored_for_seals=true")
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
