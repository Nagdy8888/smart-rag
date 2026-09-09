"""Live Hybrid retrieve/answer helpers for private PDF eval CLIs.

Never prints questions, answers, glossary values, or excerpts.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from uuid import UUID

import psycopg
from smart_rag_agents.prompts import (
    answer_prompt_text,
    eval_pdf_judge_prompt_text,
    rerank_prompt_text,
)
from smart_rag_agents.query.runtime.adapters import DsnBm25Retriever, context_loader
from smart_rag_core.evaluation.private_pdf import (
    PrivatePdfLabeledCase,
    PrivatePdfQueryClass,
    aggregate_retrieve_gates,
    score_agent_case,
    score_retrieve_case,
)
from smart_rag_core.evaluation.private_pdf.agent_scores import (
    FAITHFULNESS_GATE,
    UNSCORED,
    aggregate_agent_gates,
)
from smart_rag_core.evaluation.private_pdf.metrics import PrivatePdfRetrieveScore
from smart_rag_core.gateways.embedding import create_embedding_gateway
from smart_rag_core.gateways.model import (
    AnswerModelRequest,
    AnswerModelResponse,
    create_model_gateway,
)
from smart_rag_core.gateways.openai_answer import (
    OpenAIAnswerError,
    execute_openai_pdf_eval_judge,
)
from smart_rag_core.query_answer.assembly import assemble_source_records
from smart_rag_core.query_answer.generate import filter_invented_ids
from smart_rag_core.query_answer.models import AnswerPayload
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    EVAL_JUDGE_MODEL_ID,
    EVAL_PDF_JUDGE_PROMPT_SHA256,
    EVAL_PDF_JUDGE_PROMPT_VERSION,
)
from smart_rag_core.query_fusion.config_hash import fusion_config_hash
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.retrieval.coverage import CoverageDecision
from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_PROFILE_ID,
    UnknownRetrievalProfileError,
    load_evaluation_profile,
    load_frozen_profile,
)
from smart_rag_core.retrieval.hybrid_run import HybridRetriever, HybridRunResult
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.reranker import rerank_pool
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.settings import SharedSettings

from tests.contract.integration_support import (
    packet8_paradedb_url,
    paradedb_host_reachable,
    try_connect,
)

EXACT_DEFAULT = PrivatePdfQueryClass.EXACT_ACRONYM.value


class _DsnChannelMarker:
    """Truthy Hybrid channel flag. Per-channel jobs open their own DSN connections."""

    retrieve = None


def candidate_digest(profile_id: str) -> str:
    """Return the canonical digest of an evaluation or frozen profile file.

    Args:
        profile_id: Profile id.

    Returns:
        SHA-256 hex.

    Raises:
        UnknownRetrievalProfileError: Unknown id.
    """

    from smart_rag_core.retrieval.frozen_profile import (
        CANDIDATE_PROFILE_PATH,
        FROZEN_PROFILE_PATH,
        canonical_profile_digest,
    )

    if profile_id == HYBRID_DEFAULT_PROFILE_ID:
        path = FROZEN_PROFILE_PATH
    elif profile_id == LONG_DOCUMENT_PROFILE_ID:
        path = CANDIDATE_PROFILE_PATH
    else:
        raise UnknownRetrievalProfileError(profile_id)
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise UnknownRetrievalProfileError(profile_id)
    return canonical_profile_digest(raw)


def load_profile_for_eval(profile_id: str) -> object:
    """Load a frozen profile when allow-listed, else the evaluation candidate.

    Args:
        profile_id: Frozen or candidate id.

    Returns:
        Validated profile object.
    """

    try:
        return load_frozen_profile(profile_id)
    except UnknownRetrievalProfileError:
        return load_evaluation_profile(profile_id)


def bind_live_rerank(settings: SharedSettings) -> Callable[..., object]:
    """Bind production ``rerank_pool`` with the pinned ``rerank_v1`` prompt.

    Args:
        settings: Process settings with a live OpenAI key.

    Returns:
        Rerank callback matching ``HybridRetriever``.

    Raises:
        RuntimeError: Mock mode would satisfy identity, not live rerank.
    """

    if settings.mock_model_mode:
        raise RuntimeError("mock_embeddings_not_live_hybrid")
    gateway = create_model_gateway(settings)
    prompt = rerank_prompt_text()

    def _rerank(
        query_text: str,
        pool: object,
        remaining: float,
    ) -> object:
        """Run one live rerank call.

        Args:
            query_text: User query.
            pool: Authorized rerank pool.
            remaining: Remaining deadline seconds.

        Returns:
            Rankings, usage, and fallback from ``rerank_pool``.
        """

        return rerank_pool(
            query_text,
            pool,  # type: ignore[arg-type]
            remaining,
            gateway=gateway,
            prompt_text=prompt,
        )

    return _rerank


def fusion_from_hybrid(result: HybridRunResult) -> FusionResult:
    """Build Hybrid-effective fusion evidence for one answer call.

    Args:
        result: Hybrid retrieve result.

    Returns:
        Fusion result with graph unused.
    """

    evidence: list[ScoredPassage] = []
    for rank, unit in enumerate(result.evidence, start=1):
        text = unit.citation_text[:16_000]
        evidence.append(
            ScoredPassage(
                chunk_id=str(unit.chunk_id),
                document_id=str(unit.document_id),
                version_id=str(unit.version_id),
                citation_text=text,
                hybrid_rank=rank,
                combined_score=1.0 / float(rank),
                origin=PassageOrigin.HYBRID,
                graph_discovered_only=False,
                section_path=unit.locator.section_path,
                page_number=unit.locator.page_number,
                sheet_name=unit.locator.sheet_name,
                range_ref=unit.locator.range_ref,
                source_url=unit.locator.source_url,
            )
        )
    algorithm = FusionAlgorithm.RESOLVED_PATH_FUSION
    return FusionResult(
        algorithm=algorithm,
        config_hash=fusion_config_hash(algorithm),
        requested_route="hybrid",
        effective_route="hybrid",
        fallback_reason=None,
        evidence=tuple(evidence),
        graph_discovered_only_ratio=0.0,
    )


def generate_live_answer(
    *,
    settings: SharedSettings,
    query: str,
    result: HybridRunResult,
) -> AnswerPayload:
    """Generate one grounded answer from Hybrid evidence.

    Args:
        settings: Process settings.
        query: Case question. Never logged.
        result: Hybrid retrieve result.

    Returns:
        Filtered answer payload. Empty evidence is a typed refusal.
    """

    fusion = fusion_from_hybrid(result)
    if not fusion.evidence:
        return AnswerPayload(
            answer_text="Insufficient authorized evidence.",
            status="refused",
            answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
    gateway = create_model_gateway(settings)
    records = assemble_source_records(fusion, ())
    request = AnswerModelRequest(
        query=query[:2000] or "query",
        prompt_version=ANSWER_PROMPT_VERSION,
        prompt_sha256=ANSWER_PROMPT_SHA256,
        prompt_text=answer_prompt_text(),
        source_records=records or " ",
        chunk_ids=tuple(item.chunk_id for item in fusion.evidence),
        remaining_deadline_seconds=25.0,
    )

    async def _call() -> object:
        """Await one answer call.

        Returns:
            Gateway response.
        """

        return await gateway.generate_answer(request)

    response = asyncio.run(_call())
    if not isinstance(response, AnswerModelResponse):
        return AnswerPayload(
            answer_text="Insufficient authorized evidence.",
            status="refused",
            answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
    payload = AnswerPayload.model_validate(response.payload)
    filtered = filter_invented_ids(payload, fusion, ())
    return filtered.model_copy(
        update={"answer_origin": KnowledgeScope.COMPANY_DOCUMENTS}
    )


def judge_pdf_answer(
    *,
    query: str,
    answer_text: str,
    atomic_facts: Sequence[str],
    excerpt_ids: Sequence[str],
    excerpts: Sequence[str],
) -> tuple[str, float | None]:
    """Run one bounded ``eval_pdf_judge_v1`` call. Never uses ``eval_judge_v1``.

    Args:
        query: Case question. Never logged.
        answer_text: Model answer. Never logged.
        atomic_facts: Approved facts. Never logged.
        excerpt_ids: Evidence ids.
        excerpts: Bounded canonical excerpts. Never logged.

    Returns:
        ``(complete, faithfulness)`` or ``(unscored, None)``.
    """

    prompt = eval_pdf_judge_prompt_text()
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    if digest != EVAL_PDF_JUDGE_PROMPT_SHA256:
        return UNSCORED, None
    settings = SharedSettings()
    secret = settings.openai_api_key
    if secret is None:
        return UNSCORED, None
    user_payload: dict[str, object] = {
        "question": query[:2000],
        "atomic_facts": list(atomic_facts)[:16],
        "answer_text": answer_text[:8_000],
        "evidence_ids": list(excerpt_ids)[:24],
        "excerpts": list(excerpts)[:12],
    }
    try:
        payload, _request_id, _in_tok, _out_tok = execute_openai_pdf_eval_judge(
            api_key=secret.get_secret_value(),
            prompt_text=prompt,
            prompt_sha256=digest,
            prompt_version=EVAL_PDF_JUDGE_PROMPT_VERSION,
            model_id=EVAL_JUDGE_MODEL_ID,
            user_payload=user_payload,
            timeout_seconds=30.0,
        )
    except OpenAIAnswerError:
        return UNSCORED, None
    status = str(payload.get("status", "")).strip()
    if status != "complete":
        return UNSCORED, None
    try:
        faith = float(payload.get("faithfulness"))
    except (TypeError, ValueError):
        return UNSCORED, None
    if faith < 0.0 or faith > 1.0:
        return UNSCORED, None
    return "complete", faith


class PdfEvalRuntime:
    """Hosted Hybrid retrieve for one sealed PDF version.

    Holds live embeddings, ParadeDB BM25, and the production rerank callback.
    """

    def __init__(
        self,
        *,
        supabase_url: str,
        parade_url: str,
        settings: SharedSettings,
        version_id: UUID,
        current_chunk_ids: frozenset[UUID],
        live_rerank: bool,
    ) -> None:
        """Bind connections and gateways.

        Args:
            supabase_url: Operator DSN.
            parade_url: Local ParadeDB URL.
            settings: Shared settings.
            version_id: Ingested PDF version.
            current_chunk_ids: Authorized representative ids for ACL checks.
            live_rerank: True binds ``rerank_pool``; false is identity.

        Raises:
            RuntimeError: Mock mode or missing infrastructure.
        """

        if settings.mock_model_mode:
            raise RuntimeError("mock_embeddings_not_live_hybrid")
        self._supabase_url = supabase_url
        self._parade_url = parade_url
        self._settings = settings
        self.version_id = version_id
        self.current_chunk_ids = current_chunk_ids
        self._embedding = create_embedding_gateway(settings)
        self._rerank = bind_live_rerank(settings) if live_rerank else None
        self._live_rerank = live_rerank

    def retrieve_labeled(
        self,
        labeled: Sequence[PrivatePdfLabeledCase],
        *,
        default_profile_id: str,
        long_profile_id: str,
    ) -> tuple[list[PrivatePdfRetrieveScore], list[HybridRunResult]]:
        """Retrieve every labeled row. Does not print queries.

        Args:
            labeled: Sealed labeled cases.
            default_profile_id: Profile for exact acronym rows.
            long_profile_id: Profile for non-trivial rows.

        Returns:
            Per-case scores and Hybrid results aligned with ``labeled``.
        """

        scores: list[PrivatePdfRetrieveScore] = []
        results: list[HybridRunResult] = []
        default_profile = load_profile_for_eval(default_profile_id)
        long_profile = load_profile_for_eval(long_profile_id)
        bm25 = DsnBm25Retriever(self._parade_url)
        for row in labeled:
            actor = row.meta.acl_actor_id
            if actor is None:
                raise RuntimeError("acl_actor_required")
            with psycopg.connect(self._supabase_url, autocommit=True) as lookup:
                lookup.execute("SET ROLE postgres")
                role_row = lookup.execute(
                    """
                    SELECT role::text, app.current_authorization_version()
                    FROM app.profiles
                    WHERE user_id = %s::uuid
                    """,
                    (actor,),
                ).fetchone()
            if role_row is None:
                raise RuntimeError("acl_actor_missing")
            caller = CallerContext(
                user_id=actor,
                role=UserRole(str(role_row[0])),
                authorization_version=int(str(role_row[1])),
            )
            wanted = row.meta.expected_profile_id
            profile = (
                default_profile if wanted == default_profile_id else long_profile
            )
            retriever = HybridRetriever(
                embedding_gateway=self._embedding,
                supabase=None,
                paradedb=None,
                supabase_dsn=self._supabase_url,
                dense=_DsnChannelMarker(),
                bm25=bm25,
                term=_DsnChannelMarker(),
                load_context=context_loader(self._supabase_url, caller),
                rerank=self._rerank,  # type: ignore[arg-type]
                retrieval_profile=profile,  # type: ignore[arg-type]
            )
            result = retriever.retrieve(
                query=row.question,
                caller=caller,
                restrict_version_id=self.version_id,
            )
            results.append(result)
            acl_leak = any(
                chunk_id not in self.current_chunk_ids for chunk_id in result.ranked_ids
            )
            pages = tuple(
                int(unit.locator.page_number)
                for unit in result.evidence
                if unit.locator.page_number is not None
            )
            scores.append(
                score_retrieve_case(
                    case_id=row.meta.case_id,
                    query_class=row.meta.query_class,
                    ranked_ids=result.ranked_ids,
                    gold_ids=row.meta.chunk_ids,
                    gold_pages=row.meta.page_numbers,
                    evidence_pages=pages,
                    expected_refusal=row.meta.expected_refusal,
                    refused=result.coverage.decision is CoverageDecision.REFUSE,
                    acl_leak=acl_leak,
                    required_terms=row.meta.required_terms,
                    first_evidence_ms=result.first_evidence_ms,
                    rerank_call_count=result.rerank_call_count,
                    bm25_fallback=str(result.fallback_reason),
                )
            )
        return scores, results


def build_retrieve_report(
    labeled: Sequence[PrivatePdfLabeledCase],
    scores: Sequence[PrivatePdfRetrieveScore],
    *,
    candidate_profile_id: str,
    runtime_allow_listed: bool,
    live_rerank: bool,
) -> dict[str, object]:
    """Aggregate retrieve gates without private text.

    Args:
        labeled: Scored cases.
        scores: Per-case scores.
        candidate_profile_id: Profile under test.
        runtime_allow_listed: Whether ``load_frozen_profile`` accepts it.
        live_rerank: Whether the production reranker was bound.

    Returns:
        Git-safe report.
    """

    counts: dict[str, int] = {}
    for row in labeled:
        counts[row.meta.query_class] = counts.get(row.meta.query_class, 0) + 1
    report = aggregate_retrieve_gates(tuple(scores), class_counts=counts)
    report["candidate_profile_id"] = candidate_profile_id
    report["candidate_digest"] = candidate_digest(candidate_profile_id)
    report["runtime_allow_listed"] = runtime_allow_listed
    report["human_sealed"] = True
    report["live_rerank"] = live_rerank
    report["identity_labelled_live_rerank"] = False
    return report


def score_agent_rows(
    labeled: Sequence[PrivatePdfLabeledCase],
    results: Sequence[HybridRunResult],
    answers: Sequence[AnswerPayload],
    judge_pairs: Sequence[tuple[str, float | None]],
) -> dict[str, object]:
    """Aggregate deterministic plus judge agent gates.

    Args:
        labeled: Sealed labeled cases.
        results: Hybrid results aligned with cases.
        answers: Answer payloads aligned with cases.
        judge_pairs: Judge status/score aligned with cases.

    Returns:
        Git-safe agent report. ``holdout_opened`` stays false here.
    """

    scores = []
    for row, result, answer, judge in zip(labeled, results, answers, judge_pairs, strict=True):
        cited: list[UUID] = []
        for citation in answer.citations:
            if citation.chunk_id:
                cited.append(UUID(str(citation.chunk_id)))
        fact_ids = tuple((row.meta.chunk_ids,) for _ in row.atomic_facts) or (
            (row.meta.chunk_ids,)
            if row.meta.chunk_ids
            else ()
        )
        pages = tuple(
            int(unit.locator.page_number)
            for unit in result.evidence
            if unit.locator.page_number is not None
        )
        locator_ok = bool(row.meta.chunk_ids) and all(
            item in set(result.ranked_ids[:12]) for item in row.meta.chunk_ids
        )
        if row.meta.page_numbers and pages:
            locator_ok = locator_ok and bool(set(row.meta.page_numbers) & set(pages))
        expected_profile = row.meta.expected_profile_id
        route_ok = result.retrieval_profile_id == expected_profile
        if row.meta.query_class != EXACT_DEFAULT:
            route_ok = result.retrieval_profile_id == LONG_DOCUMENT_PROFILE_ID
            route_ok = route_ok and result.rerank_call_count == 1
            route_ok = route_ok and str(result.rerank_fallback) in {"", "none"}
            route_ok = route_ok and str(result.fallback_reason) == "none"
        refused = answer.status == "refused" or (
            result.coverage.decision is CoverageDecision.REFUSE
        )
        scores.append(
            score_agent_case(
                case_id=row.meta.case_id,
                cited_ids=cited,
                allowed_ids=row.meta.chunk_ids,
                fact_chunk_ids=fact_ids,
                forbidden_ids=(),
                locator_ok=locator_ok or (row.meta.expected_refusal and refused),
                route_ok=route_ok,
                expected_refusal=row.meta.expected_refusal,
                refused=refused,
                judge_status=judge[0],
                judge_faithfulness=judge[1],
            )
        )
    report = aggregate_agent_gates(tuple(scores))
    faith = report.get("mean_judge_faithfulness")
    report["judge_prompt"] = EVAL_PDF_JUDGE_PROMPT_VERSION
    report["eval_judge_v1_reused"] = False
    report["agent_gates_pass"] = bool(report.get("deterministic_pass")) and (
        isinstance(faith, float)
        and faith >= FAITHFULNESS_GATE
        and int(str(report.get("judge_unscored_count", 1))) == 0
    )
    return report


def probe_infra(supabase_url: str) -> tuple[str, str] | None:
    """Return ParadeDB URL when both stores accept a probe.

    Args:
        supabase_url: Operator DSN.

    Returns:
        ``(supabase_url, parade_url)`` or None.
    """

    parade_url = packet8_paradedb_url()
    probe = try_connect(supabase_url)
    if probe is None or parade_url is None or not paradedb_host_reachable():
        return None
    probe.close()
    return supabase_url, parade_url


def load_current_chunk_ids(supabase_url: str, version_id: UUID) -> frozenset[UUID]:
    """Load current representative chunk ids.

    Args:
        supabase_url: Operator DSN.
        version_id: Ingested version.

    Returns:
        Chunk ids.
    """

    with psycopg.connect(supabase_url, connect_timeout=20) as connection:
        connection.execute("SET ROLE postgres")
        rows = connection.execute(
            """
            SELECT id
            FROM app.document_chunks
            WHERE version_id = %s::uuid
              AND deleted_at IS NULL
              AND is_search_representative
            """,
            (version_id,),
        ).fetchall()
    return frozenset(UUID(str(row[0])) for row in rows)


def write_report(path: Path, report: dict[str, object]) -> None:
    """Write a gitignored JSON report.

    Args:
        path: Destination.
        report: Aggregates only.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")


def print_retrieve_stdout(report: dict[str, object]) -> None:
    """Print gate tokens only.

    Args:
        report: Retrieve aggregates.
    """

    print(f"case_count={report['case_count']}")
    print(f"hybrid_recall_at_10={report['hybrid_recall_at_10']}")
    print(f"exact_term_recall_at_5={report['exact_term_recall_at_5']}")
    print(f"alias_recall_at_10={report['alias_recall_at_10']}")
    print(f"locator_correctness={report['locator_correctness']}")
    print(f"first_evidence_p95_ms={report['first_evidence_p95_ms']}")
    print(f"acl_leaks={report['acl_leaks']}")
    print(f"eligible_rerank_ones={report.get('eligible_rerank_ones')}")
    print(f"fallback_histogram={report.get('fallback_histogram')}")
    print(f"live_rerank={report.get('live_rerank')}")
    print(f"candidate_profile_id={report.get('candidate_profile_id')}")
    print(f"candidate_digest={report.get('candidate_digest')}")
    print("holdout_opened=false")
    print(f"runtime_allow_listed={report.get('runtime_allow_listed')}")
    print("human_sealed=true")
