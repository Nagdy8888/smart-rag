"""Evaluator-only oracle: answer from approved gold chunks after ACL recheck.

Loads approved chunk IDs through ``fetch_authorized_chunk_context``, builds
``HybridPassage`` evidence, then runs the production answer plus verifier
path with ``answer_v3`` / ``verifier_v2`` and
``render_verified_company_answer``. Never embeds sample gold in production
modules. Prints counts only.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_agents.prompts import (  # noqa: E402
    answer_prompt_text,
    verifier_prompt_text,
)
from smart_rag_agents.query.gateway.verifier import (  # noqa: E402
    parse_verifier_payload,
)
from smart_rag_core.evaluation.company_ask_regression import (  # noqa: E402
    AskRegressionConfigError,
    CompanyAskQuestion,
    load_private_gold,
)
from smart_rag_core.evaluation.dual_metric import (  # noqa: E402
    DualMetricScore,
    RetrievalStageAttribution,
    SourceResolutionStage,
    score_company_answer,
)
from smart_rag_core.gateways.model import (  # noqa: E402
    AnswerModelRequest,
    AnswerModelResponse,
    VerifierModelRequest,
    VerifierModelResponse,
    create_model_gateway,
)
from smart_rag_core.query_answer.assembly import (  # noqa: E402
    assemble_source_records,
    fit_source_records,
)
from smart_rag_core.query_answer.generate import generate_answer  # noqa: E402
from smart_rag_core.query_answer.models import (  # noqa: E402
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_answer.release import (  # noqa: E402
    render_verified_company_answer,
)
from smart_rag_core.query_answer.sanitize import filter_invented_ids  # noqa: E402
from smart_rag_core.query_answer.verifier import run_verifier_batch  # noqa: E402
from smart_rag_core.query_answer.versions import (  # noqa: E402
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
)
from smart_rag_core.query_fusion.config_hash import fusion_config_hash  # noqa: E402
from smart_rag_core.query_fusion.models import (  # noqa: E402
    FusionAlgorithm,
    FusionResult,
    HybridPassage,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope  # noqa: E402
from smart_rag_core.retrieval.context_loader import (  # noqa: E402
    ChunkContext,
    fetch_authorized_chunk_context,
)
from smart_rag_core.security.identity import CallerContext, UserRole  # noqa: E402
from smart_rag_core.settings import SharedSettings  # noqa: E402

from scripts.pdf_eval_cli import apply_merged_env, operator_url  # noqa: E402

_CITATION_CAP = 16_000


def json_mapping(value: object) -> dict[str, object]:
    """Coerce a JSON object to a string-keyed mapping.

    Args:
        value: Parsed JSON value.

    Returns:
        String-keyed mapping, or empty when the value is not an object.
    """

    if not isinstance(value, dict):
        return {}
    typed = cast(dict[object, object], value)
    return {str(key): item for key, item in typed.items()}


def load_slice_chunk_ids(path: Path) -> dict[str, tuple[UUID, ...]]:
    """Load approved isolation-slice chunk IDs from a private JSON file.

    Args:
        path: Gitignored slice file. Must live under ``.private-eval/``.

    Returns:
        Question id to ordered unique chunk IDs.

    Raises:
        AskRegressionConfigError: Path is not private or the payload is invalid.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise AskRegressionConfigError("slice gold must live under .private-eval")
    payload_obj: object = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload_obj, list):
        raise AskRegressionConfigError("slice file must be a JSON array")
    out: dict[str, tuple[UUID, ...]] = {}
    for raw in cast(list[object], payload_obj):
        if not isinstance(raw, dict):
            raise AskRegressionConfigError("slice row must be an object")
        row = json_mapping(cast(object, raw))
        question_id = str(row.get("id") or "").strip()
        chunk_raw = row.get("chunk_ids")
        if not question_id or not isinstance(chunk_raw, list):
            raise AskRegressionConfigError("slice row missing id or chunk_ids")
        unique: list[UUID] = []
        seen: set[UUID] = set()
        for item in cast(list[object], chunk_raw):
            chunk_id = UUID(str(item))
            if chunk_id in seen:
                continue
            seen.add(chunk_id)
            unique.append(chunk_id)
        out[question_id] = tuple(unique)
    return out


def lookup_eval_caller(operator_dsn: str, user_id: UUID) -> CallerContext:
    """Resolve the live evaluator ``CallerContext`` from ``app.profiles``.

    Args:
        operator_dsn: Privileged operator DSN. Never printed.
        user_id: Authenticated evaluator user id.

    Returns:
        Server-derived caller used for ACL/current-version recheck.

    Raises:
        RuntimeError: Profile row is missing.
    """

    with psycopg.connect(operator_dsn, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            """
            SELECT role::text, app.current_authorization_version()
            FROM app.profiles
            WHERE user_id = %s::uuid
            """,
            (str(user_id),),
        ).fetchone()
    if row is None:
        raise RuntimeError("acl_actor_missing")
    return CallerContext(
        user_id=str(user_id),
        role=UserRole(str(row[0])),
        authorization_version=int(str(row[1])),
    )


def resolve_eval_user_id(operator_dsn: str, email: str) -> UUID:
    """Look up the evaluator user id by email without printing it.

    Args:
        operator_dsn: Privileged operator DSN.
        email: Evaluator email from private credentials.

    Returns:
        Auth user UUID.

    Raises:
        RuntimeError: No matching auth user.
    """

    with psycopg.connect(operator_dsn, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        row = connection.execute(
            """
            SELECT id
            FROM auth.users
            WHERE lower(email) = lower(%s)
            LIMIT 1
            """,
            (email,),
        ).fetchone()
    if row is None:
        raise RuntimeError("eval_user_missing")
    return UUID(str(row[0]))


def load_authorized_gold(
    *,
    operator_dsn: str,
    caller: CallerContext,
    chunk_ids: Sequence[UUID],
) -> tuple[ChunkContext, ...]:
    """Recheck approved gold IDs through the ACL/current-version RPC.

    Args:
        operator_dsn: Privileged login that can ``SET LOCAL ROLE app_api``.
        caller: Evaluator identity.
        chunk_ids: Approved gold IDs.

    Returns:
        Authorized current-version rows. Unauthorized IDs are omitted.
    """

    if not chunk_ids:
        return ()
    with psycopg.connect(operator_dsn, autocommit=True) as connection:
        connection.execute("SET ROLE postgres")
        return fetch_authorized_chunk_context(
            connection,
            caller=caller,
            chunk_ids=tuple(chunk_ids),
        )


def hybrid_passages_from_context(
    rows: Sequence[ChunkContext],
) -> tuple[HybridPassage, ...]:
    """Build ranked Hybrid passages from ACL-rechecked gold context.

    Args:
        rows: Authorized chunk rows in request order.

    Returns:
        Frozen Hybrid passages. Citation text is canonical ``raw_text``.
    """

    passages: list[HybridPassage] = []
    for rank, row in enumerate(rows, start=1):
        passages.append(
            HybridPassage(
                chunk_id=str(row.chunk_id),
                document_id=str(row.document_id),
                version_id=str(row.version_id),
                citation_text=row.raw_text[:_CITATION_CAP],
                hybrid_rank=rank,
                section_path=row.section_path,
                page_number=row.page_number,
                sheet_name=row.sheet_name,
                range_ref=row.range_ref,
                source_url=row.source_url,
                authorized_current=True,
            )
        )
    return tuple(passages)


def fusion_from_hybrid_passages(passages: Sequence[HybridPassage]) -> FusionResult:
    """Convert Hybrid passages into Hybrid-effective fusion evidence.

    Args:
        passages: ACL-rechecked gold passages.

    Returns:
        Fusion result with graph unused.
    """

    evidence: list[ScoredPassage] = []
    for item in passages:
        evidence.append(
            ScoredPassage(
                chunk_id=item.chunk_id,
                document_id=item.document_id,
                version_id=item.version_id,
                citation_text=item.citation_text,
                hybrid_rank=item.hybrid_rank,
                combined_score=1.0 / float(item.hybrid_rank),
                origin=PassageOrigin.HYBRID,
                graph_discovered_only=False,
                section_path=item.section_path,
                page_number=item.page_number,
                sheet_name=item.sheet_name,
                range_ref=item.range_ref,
                source_url=item.source_url,
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


def _live_answer_caller(
    settings: SharedSettings,
    *,
    user_query: str,
) -> object:
    """Bind one production answer adapter.

    Args:
        settings: Process settings with a live model key.
        user_query: Original question. Never logged.

    Returns:
        Callable matching ``AnswerCaller``.
    """

    gateway = create_model_gateway(settings)
    prompt = answer_prompt_text()

    def _call(
        records: str,
        fusion: FusionResult,
        tables: tuple[object, ...],
    ) -> AnswerPayload:
        """Issue one counted answer generation.

        Args:
            records: Fitted delimited source records from generation.
            fusion: Oracle gold evidence after input fitting.
            tables: Unused table snapshots.

        Returns:
            Parsed answer payload before verifier/release.
        """

        del tables
        request = AnswerModelRequest(
            query=user_query[:2000] or "query",
            prompt_version=ANSWER_PROMPT_VERSION,
            prompt_sha256=ANSWER_PROMPT_SHA256,
            prompt_text=prompt,
            source_records=records or " ",
            chunk_ids=tuple(item.chunk_id for item in fusion.evidence),
            remaining_deadline_seconds=25.0,
        )

        async def _await() -> object:
            """Await the gateway answer.

            Returns:
                Gateway response.
            """

            return await gateway.generate_answer(request)

        response = asyncio.run(_await())
        if not isinstance(response, AnswerModelResponse):
            return AnswerPayload(
                answer_text="Insufficient authorized evidence.",
                status="refused",
                answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
            )
        return AnswerPayload.model_validate(response.payload)

    return _call


def _live_verifier_caller(settings: SharedSettings, fusion: FusionResult) -> object:
    """Bind one production verifier adapter for the current fusion.

    Args:
        settings: Process settings with a live model key.
        fusion: Oracle gold evidence shown to the verifier.

    Returns:
        Callable matching ``VerifierCaller``.
    """

    gateway = create_model_gateway(settings)
    prompt = verifier_prompt_text()
    records = assemble_source_records(fusion, ())[:12_000]

    def _call(links: tuple[AtomicLink, ...]) -> object:
        """Issue one verifier batch.

        Args:
            links: At most six material links.

        Returns:
            Structured verifier payload.
        """

        request = VerifierModelRequest(
            prompt_version=VERIFIER_PROMPT_VERSION,
            prompt_sha256=VERIFIER_PROMPT_SHA256,
            prompt_text=prompt,
            source_records=records or " ",
            links=tuple(
                cast(dict[str, object], item.model_dump(mode="json")) for item in links
            ),
            remaining_deadline_seconds=20.0,
        )

        async def _await() -> object:
            """Await the gateway verifier.

            Returns:
                Gateway response.
            """

            return await gateway.generate_verifier(request)

        response = asyncio.run(_await())
        payload: object
        if isinstance(response, VerifierModelResponse):
            payload = response.payload
        else:
            payload = getattr(response, "payload", None)
        return parse_verifier_payload(payload)

    return _call


def run_oracle_answer(
    *,
    settings: SharedSettings,
    query: str,
    passages: Sequence[HybridPassage],
) -> tuple[AnswerPayload, int, int]:
    """Generate, verify, and release one company answer from oracle passages.

    Args:
        settings: Live model settings.
        query: User question. Never logged.
        passages: ACL-rechecked gold passages.

    Returns:
        Released payload, authorized passage count, and verifier call count.

    State Inputs:
        Oracle gold IDs already rechecked. No Hybrid retrieve.

    State Outputs:
        Verified company answer. Citations come only from surviving links.

    Persistence Writes:
        None.

    External/Model Calls:
        One ``answer_v3`` generation and at most one ``verifier_v2`` batch.

    Budget/Deadline:
        Answer 25s, verifier 20s. No second generation.

    Failure/Fallback:
        Empty authorized evidence returns a citation-free refusal.
    """

    fusion = fusion_from_hybrid_passages(passages)
    fit = fit_source_records(
        user_query=query,
        fusion=fusion,
        tables=(),
        max_input_chars=16_384,
        route=fusion.effective_route,
    )
    fusion = fit.fusion
    if not fusion.evidence:
        refused = AnswerPayload(
            answer_text="Insufficient authorized evidence.",
            status="refused",
            answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        )
        return refused, 0, 0
    generated = generate_answer(
        fusion=fusion,
        tables=(),
        user_query=query,
        caller=_live_answer_caller(settings, user_query=query),  # type: ignore[arg-type]
        already_generated=0,
        company_claim_forbidden=False,
        graph_as_answer_forbidden=False,
        knowledge_scope=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    filtered = filter_invented_ids(generated, fusion, ())
    verifier = _live_verifier_caller(settings, fusion)
    checked, verifier_calls, _omitted = run_verifier_batch(
        filtered,
        caller=verifier,  # type: ignore[arg-type]
        already_called=0,
    )
    released = render_verified_company_answer(checked, fusion=fusion, tables=())
    return released, len(fusion.evidence), verifier_calls


def score_oracle_answer(
    question: CompanyAskQuestion,
    payload: AnswerPayload,
    *,
    authorized_count: int,
) -> DualMetricScore:
    """Score one oracle answer with dual metrics.

    Args:
        question: Private gold question.
        payload: Released answer.
        authorized_count: ACL-rechecked passage count.

    Returns:
        Dual-metric score. Channel hits are unused on the oracle path.
    """

    stages = RetrievalStageAttribution(
        source_resolution=SourceResolutionStage.EXACT_ONE,
        fused_count=authorized_count,
        retrieval_empty=authorized_count == 0,
        verifier_status=payload.status,
    )
    return score_company_answer(
        answer_text=payload.answer_text,
        facts=question.facts,
        stages=stages,
        answer_status=payload.status,
    )


def load_credentials_email(path: Path) -> str:
    """Read the evaluator email from a private credentials file.

    Args:
        path: Gitignored credentials JSON.

    Returns:
        Email string.

    Raises:
        AskRegressionConfigError: Missing private email.
    """

    resolved = path.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        raise AskRegressionConfigError("credentials must live under .private-eval")
    payload = json_mapping(json.loads(resolved.read_text(encoding="utf-8")))
    email = str(payload.get("email") or "").strip()
    if not email:
        raise AskRegressionConfigError("credentials email missing")
    return email


def main(argv: list[str] | None = None) -> int:
    """Run the oracle arm for each private gold question.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` when every question received an ACL recheck and a scored answer.
        ``2`` on configuration or ACL-recheck failure.
    """

    parser = argparse.ArgumentParser(
        description=(
            "Answer from approved gold chunks after ACL/current-version recheck."
        )
    )
    parser.add_argument("--gold", type=Path, required=True)
    parser.add_argument("--slice", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--credentials", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        env = apply_merged_env()
        questions = load_private_gold(args.gold)
        slice_ids = load_slice_chunk_ids(args.slice)
        email = load_credentials_email(args.credentials)
        operator_dsn = operator_url(env)
        user_id = resolve_eval_user_id(operator_dsn, email)
        caller = lookup_eval_caller(operator_dsn, user_id)
        settings = SharedSettings()
        if settings.mock_model_mode:
            print("blocked=mock_model_mode", file=sys.stderr)
            return 2
    except (
        AskRegressionConfigError,
        OSError,
        json.JSONDecodeError,
        RuntimeError,
    ) as exc:
        print(f"blocked={exc}", file=sys.stderr)
        return 2

    outcomes: list[dict[str, object]] = []
    authorized_ok = 0
    grounded = 0
    strict = 0
    empty_acl = 0
    for question in questions:
        wanted = slice_ids.get(question.question_id, ())
        try:
            rows = load_authorized_gold(
                operator_dsn=operator_dsn,
                caller=caller,
                chunk_ids=wanted,
            )
        except Exception as exc:
            print(f"blocked=acl_recheck_failed:{type(exc).__name__}", file=sys.stderr)
            return 2
        if wanted and len(rows) != len(wanted):
            print("blocked=acl_recheck_dropped_gold", file=sys.stderr)
            return 2
        if not rows:
            empty_acl += 1
            payload = AnswerPayload(
                answer_text="Insufficient authorized evidence.",
                status="refused",
                answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
            )
            authorized_count = 0
            verifier_calls = 0
        else:
            authorized_ok += 1
            passages = hybrid_passages_from_context(rows)
            try:
                payload, authorized_count, verifier_calls = run_oracle_answer(
                    settings=settings,
                    query=question.prompt,
                    passages=passages,
                )
            except Exception as exc:
                print(f"oracle_error={type(exc).__name__}", flush=True)
                payload = AnswerPayload(
                    answer_text="Insufficient authorized evidence.",
                    status="refused",
                    answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
                )
                authorized_count = len(rows)
                verifier_calls = 0
        score = score_oracle_answer(
            question,
            payload,
            authorized_count=authorized_count,
        )
        if score.grounded_fact_pass:
            grounded += 1
        if score.strict_pass:
            strict += 1
        outcomes.append(
            {
                "question_id": question.question_id,
                "requested_gold": len(wanted),
                "authorized_gold": authorized_count,
                "acl_recheck": True,
                "verifier_calls": verifier_calls,
                "answer_status": payload.status,
                "citation_count": len(payload.citations),
                "strict_pass": score.strict_pass,
                "grounded_fact_pass": score.grounded_fact_pass,
                "deadline_failure": score.deadline_failure,
                "empty_retrieval": score.empty_retrieval,
                "answer_chars": len(payload.answer_text),
            }
        )

    summary: dict[str, object] = {
        "arm": "B",
        "questions": len(questions),
        "authorized_ok": authorized_ok,
        "acl_empty": empty_acl,
        "acl_recheck": True,
        "strict_pass": strict,
        "grounded_fact_pass": grounded,
        "prompt_versions": {
            "answer": ANSWER_PROMPT_VERSION,
            "verifier": VERIFIER_PROMPT_VERSION,
        },
        "holdout_opened": False,
        "outcomes": outcomes,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "arm": "B",
                "questions": len(questions),
                "authorized_ok": authorized_ok,
                "acl_empty": empty_acl,
                "acl_recheck": True,
                "strict_pass": strict,
                "grounded_fact_pass": grounded,
                "holdout_opened": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
