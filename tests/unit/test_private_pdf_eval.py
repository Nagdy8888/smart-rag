"""Unit tests for private PDF eval sealing, drafts, and source-scope fail-closed."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from smart_rag_core.evaluation.holdout import HoldoutSealedError
from smart_rag_core.evaluation.private_pdf import (
    MINIMUM_SEALED_CASES,
    NOT_APPLICABLE,
    PRIVATE_PDF_CLASS_MINIMUMS,
    ChunkLocator,
    PrivatePdfCase,
    PrivatePdfQueryClass,
    PrivatePdfSealError,
    aggregate_agent_gates,
    aggregate_retrieve_gates,
    assert_current_chunk_ids,
    assert_holdout_path_hidden,
    build_draft_rows,
    families_are_disjoint,
    load_private_pdf_labeled_open_splits,
    load_private_pdf_tuning_cases,
    manifest_hash,
    near_duplicate_pairs,
    question_hash,
    score_agent_case,
    score_retrieve_case,
    seal_cases,
)
from smart_rag_core.retrieval.frozen_profile import (
    LONG_DOCUMENT_PROFILE_ID,
    UnknownRetrievalProfileError,
    load_frozen_profile,
)
from smart_rag_core.retrieval.profiles import HYBRID_DEFAULT_PROFILE_ID
from smart_rag_core.retrieval.source_scope import (
    SourceResolution,
    resolve_retrieval_scope,
)
from smart_rag_core.security.identity import CallerContext, UserRole

REPO_ROOT = Path(__file__).resolve().parents[2]
EVAL_HYBRID = REPO_ROOT / "scripts" / "eval_pdf_hybrid.py"
EVAL_AGENT = REPO_ROOT / "scripts" / "eval_pdf_agent.py"
_CHUNK = UUID("00000000-0000-0000-0000-000000000001")


def _case(**overrides: object) -> PrivatePdfCase:
    """Build one synthetic overlay case.

    Args:
        **overrides: Field replacements.

    Returns:
        Frozen case.
    """

    payload: dict[str, object] = {
        "case_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
        "split": "development",
        "source_family_id": "cccccccccccccccccccccccc",
        "query_class": PrivatePdfQueryClass.FACTUAL_DEFINITION.value,
        "chunk_ids": (_CHUNK,),
        "human_approved": False,
        "generated_only": True,
    }
    payload.update(overrides)
    return PrivatePdfCase.model_validate(payload)


def test_generated_labels_cannot_self_seal() -> None:
    """A model draft is never gold."""

    with pytest.raises(PrivatePdfSealError, match="generated_labels_cannot_self_seal"):
        seal_cases((_case(),))


def test_family_must_not_cross_splits() -> None:
    """Source families stay inside one split."""

    family = "cccccccccccccccccccccccc"
    cases = (
        _case(
            human_approved=True,
            generated_only=False,
            reviewer="reviewer",
            acl_actor_id="actor-1",
        ),
        _case(
            case_id="bbbbbbbbbbbbbbbbbbbbbbbb",
            split="qualification",
            source_family_id=family,
            chunk_ids=(UUID("00000000-0000-0000-0000-000000000002"),),
            human_approved=True,
            generated_only=False,
            reviewer="reviewer",
            acl_actor_id="actor-1",
        ),
    )
    assert families_are_disjoint(cases) is False
    with pytest.raises(PrivatePdfSealError, match="source_family_crosses_splits"):
        seal_cases(cases)


def test_stale_chunk_id_cannot_seal() -> None:
    """Sealing requires current authorized chunk ids."""

    case = _case(
        human_approved=True,
        generated_only=False,
        reviewer="reviewer",
        acl_actor_id="actor-1",
    )
    with pytest.raises(PrivatePdfSealError, match="stale_chunk_id"):
        assert_current_chunk_ids(
            (case,),
            current_ids=frozenset({UUID("00000000-0000-0000-0000-000000000099")}),
        )


def test_private_holdout_path_is_hidden() -> None:
    """Normal loaders cannot open private holdout custody."""

    path = Path(".private-eval") / "holdout" / "labels.json"
    with pytest.raises(HoldoutSealedError):
        assert_holdout_path_hidden(path)


def test_tuning_loader_drops_holdout_rows(
    tmp_path: Path,
) -> None:
    """Development calibration cannot materialize holdout rows."""

    path = tmp_path / "draft.json"
    path.write_text(
        """
        {"cases": [
          {
            "case_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "split": "development",
            "source_family_id": "cccccccccccccccccccccccc",
            "query_class": "factual_definition",
            "chunk_ids": ["00000000-0000-0000-0000-000000000001"],
            "generated_only": true
          },
          {
            "case_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "split": "holdout",
            "source_family_id": "dddddddddddddddddddddddd",
            "query_class": "factual_definition",
            "chunk_ids": ["00000000-0000-0000-0000-000000000002"],
            "generated_only": true
          }
        ]}
        """,
        encoding="utf-8",
    )
    loaded = load_private_pdf_tuning_cases(path)
    assert len(loaded) == 1
    assert loaded[0].split == "development"


def test_near_duplicate_detector_flags_identical_questions() -> None:
    """Exact normalized questions are near-duplicates."""

    pairs = near_duplicate_pairs(("What is Hybrid RAG?", "What is Hybrid RAG?"))
    assert pairs == ((0, 1),)


def test_eval_scripts_cannot_open_holdout() -> None:
    """Eval entrypoints stay holdout-blind."""

    for path in (EVAL_HYBRID, EVAL_AGENT):
        source = path.read_text(encoding="utf-8")
        assert "load_private_pdf_holdout" not in source
        assert "holdout_sealed" in source
        assert "prompts/eval_judge_v1.md" not in source


def test_draft_builder_meets_class_mix_and_is_deterministic() -> None:
    """Synthetic locators produce a reproducible 50+ mix with no self-seal."""

    locators = tuple(
        ChunkLocator(
            chunk_id=UUID(f"00000000-0000-0000-0000-{index:012d}"),
            page_number=index + 1,
            section_path=(f"Chapter {index // 4}", f"Section {index}"),
            raw_text=f"Agents coordinate tools. Passage {index} defines Hybrid retrieval.",
        )
        for index in range(20)
    )
    first = build_draft_rows(
        locators,
        document_hash="aa" * 32,
        aliases=("Hybrid RAG",),
        acl_actor_id="actor-1",
    )
    second = build_draft_rows(
        locators,
        document_hash="aa" * 32,
        aliases=("Hybrid RAG",),
        acl_actor_id="actor-1",
    )
    assert len(first) >= MINIMUM_SEALED_CASES
    assert [row["case_id"] for row in first] == [row["case_id"] for row in second]
    counts: dict[str, int] = {}
    for row in first:
        key = str(row["query_class"])
        counts[key] = counts.get(key, 0) + 1
        assert row["generated_only"] is True
        assert row["human_approved"] is False
        assert row["acl_actor_id"] == "actor-1"
        assert row["chunk_ids"]
    for query_class, minimum in PRIVATE_PDF_CLASS_MINIMUMS.items():
        assert counts[query_class.value] >= minimum
    questions = tuple(str(row["question"]) for row in first)
    assert len({question_hash(item) for item in questions}) == len(questions)
    refusal = [
        row
        for row in first
        if row["query_class"]
        in {
            PrivatePdfQueryClass.FULL_SUMMARY_REFUSAL.value,
            PrivatePdfQueryClass.INSUFFICIENT_OR_INJECTION.value,
        }
    ]
    assert refusal
    assert all(row["expected_refusal"] is True for row in refusal)


def test_long_document_profile_rejected_at_runtime() -> None:
    """Unfrozen candidate is not executable."""

    with pytest.raises(UnknownRetrievalProfileError):
        load_frozen_profile(LONG_DOCUMENT_PROFILE_ID)
    default = load_frozen_profile(HYBRID_DEFAULT_PROFILE_ID)
    assert default.profile_id == HYBRID_DEFAULT_PROFILE_ID


def test_source_scope_fails_closed_to_default() -> None:
    """Ambiguous sources never become hard filters; long profile stays denied."""

    caller = CallerContext(
        user_id="00000000-0000-0000-0000-000000000099",
        role=UserRole.MEMBER,
        authorization_version=1,
    )
    scope = resolve_retrieval_scope(
        caller=caller,
        requested_sources=("Unknown Book Title",),
        whole_document=True,
        representative_count=40,
    )
    assert scope.resolution is SourceResolution.UNSCOPED
    assert scope.version_id is None
    assert scope.candidate_profile_id == HYBRID_DEFAULT_PROFILE_ID
    assert scope.eligibility_reason in {
        "unfrozen_long_document_denied",
        "default_profile_required",
    }


def test_seal_requires_current_chunk_ids() -> None:
    """Live current chunk ids are required; cases cannot self-attest locators."""

    case = _case(
        human_approved=True,
        generated_only=False,
        reviewer="reviewer",
        acl_actor_id="actor-1",
    )
    with pytest.raises(PrivatePdfSealError, match="missing_current_chunk_ids"):
        seal_cases((case,), current_chunk_ids=None)


def test_acl_actor_and_named_reviewer_are_required() -> None:
    """Sealing without an ACL actor or reviewer fails closed."""

    with pytest.raises(PrivatePdfSealError, match="named_reviewer_required"):
        seal_cases(
            (
                _case(
                    human_approved=True,
                    generated_only=False,
                    acl_actor_id="actor-1",
                ),
            ),
            current_chunk_ids=frozenset({_CHUNK}),
        )
    with pytest.raises(PrivatePdfSealError, match="acl_actor_required"):
        seal_cases(
            (
                _case(
                    human_approved=True,
                    generated_only=False,
                    reviewer="reviewer",
                ),
            ),
            current_chunk_ids=frozenset({_CHUNK}),
        )


def test_langsmith_split_label_is_not_immutability(tmp_path: Path) -> None:
    """A LangSmith split label cannot make holdout rows reachable."""

    path = tmp_path / "draft.json"
    path.write_text(
        """
        {"cases": [
          {
            "case_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "split": "development",
            "langsmith_split": "holdout",
            "source_family_id": "cccccccccccccccccccccccc",
            "query_class": "factual_definition",
            "chunk_ids": ["00000000-0000-0000-0000-000000000001"],
            "generated_only": true
          }
        ]}
        """,
        encoding="utf-8",
    )
    loaded = load_private_pdf_tuning_cases(path)
    assert loaded[0].split == "development"


def test_labeled_loader_requires_question_and_drops_holdout(tmp_path: Path) -> None:
    """Labeled open-split loaders keep questions private and drop holdout."""

    path = tmp_path / "draft.json"
    path.write_text(
        """
        {"cases": [
          {
            "case_id": "aaaaaaaaaaaaaaaaaaaaaaaa",
            "split": "development",
            "source_family_id": "cccccccccccccccccccccccc",
            "query_class": "factual_definition",
            "chunk_ids": ["00000000-0000-0000-0000-000000000001"],
            "question": "What is Hybrid retrieval?",
            "generated_only": true
          },
          {
            "case_id": "bbbbbbbbbbbbbbbbbbbbbbbb",
            "split": "holdout",
            "source_family_id": "dddddddddddddddddddddddd",
            "query_class": "factual_definition",
            "chunk_ids": ["00000000-0000-0000-0000-000000000002"],
            "question": "Holdout question must not load",
            "generated_only": true
          }
        ]}
        """,
        encoding="utf-8",
    )
    loaded = load_private_pdf_labeled_open_splits(path)
    assert len(loaded) == 1
    assert loaded[0].meta.split == "development"
    assert loaded[0].question.startswith("What is")


def test_ranked_ids_not_fused_occupancy_are_recall() -> None:
    """Fused occupancy is not Recall@10."""

    gold = (_CHUNK,)
    fused_only = (UUID("00000000-0000-0000-0000-000000000099"),)
    ranked_miss = (UUID("00000000-0000-0000-0000-000000000002"),)
    miss = score_retrieve_case(
        case_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        query_class=PrivatePdfQueryClass.FACTUAL_DEFINITION.value,
        ranked_ids=ranked_miss,
        gold_ids=gold,
        gold_pages=(1,),
        evidence_pages=(1,),
        expected_refusal=False,
        refused=False,
        acl_leak=False,
    )
    assert miss.recall_hit_at_10 is False
    hit = score_retrieve_case(
        case_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        query_class=PrivatePdfQueryClass.FACTUAL_DEFINITION.value,
        ranked_ids=gold + fused_only,
        gold_ids=gold,
        gold_pages=(1,),
        evidence_pages=(1,),
        expected_refusal=False,
        refused=False,
        acl_leak=False,
    )
    assert hit.recall_hit_at_10 is True


def test_exact_class_below_minimum_is_not_applicable() -> None:
    """Exact/alias gates are not_applicable when the sealed denominator is short."""

    score = score_retrieve_case(
        case_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        query_class=PrivatePdfQueryClass.EXACT_ACRONYM.value,
        ranked_ids=(_CHUNK,),
        gold_ids=(_CHUNK,),
        gold_pages=(1,),
        evidence_pages=(1,),
        expected_refusal=False,
        refused=False,
        acl_leak=False,
        required_terms=("term",),
    )
    report = aggregate_retrieve_gates(
        (score,),
        class_counts={PrivatePdfQueryClass.EXACT_ACRONYM.value: 1},
    )
    assert report["exact_term_recall_at_5"] == NOT_APPLICABLE
    assert report["alias_recall_at_10"] == NOT_APPLICABLE


def test_unscored_judge_cannot_pass() -> None:
    """Invalid judge output is unscored and is never a faithfulness pass."""

    score = score_agent_case(
        case_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        cited_ids=(_CHUNK,),
        allowed_ids=(_CHUNK,),
        fact_chunk_ids=((_CHUNK,),),
        locator_ok=True,
        route_ok=True,
        expected_refusal=False,
        refused=False,
        judge_status="timeout",
        judge_faithfulness=1.0,
    )
    assert score.judge_status == "unscored"
    assert score.judge_faithfulness is None
    report = aggregate_agent_gates((score,))
    assert report["mean_judge_faithfulness"] == "unscored"
    assert report["judge_unscored_count"] == 1


def test_retrieve_gates_pass_requires_rerank_ones() -> None:
    """Eligible non-trivial cases must each request exactly one rerank."""

    from smart_rag_core.evaluation.private_pdf import retrieve_gates_pass

    score = score_retrieve_case(
        case_id="aaaaaaaaaaaaaaaaaaaaaaaa",
        query_class=PrivatePdfQueryClass.FACTUAL_DEFINITION.value,
        ranked_ids=(_CHUNK,),
        gold_ids=(_CHUNK,),
        gold_pages=(1,),
        evidence_pages=(1,),
        expected_refusal=False,
        refused=False,
        acl_leak=False,
        first_evidence_ms=100.0,
        rerank_call_count=0,
        bm25_fallback="none",
    )
    report = aggregate_retrieve_gates(
        (score,),
        class_counts={PrivatePdfQueryClass.FACTUAL_DEFINITION.value: 1},
    )
    assert retrieve_gates_pass(report) is False


def test_select_runtime_profile_stays_default_until_freeze() -> None:
    """Exact-one long documents stay on default until the pin exists."""

    from smart_rag_core.retrieval.source_scope import (
        SourceResolution,
        select_runtime_profile,
    )

    profile_id, reason = select_runtime_profile(
        resolution=SourceResolution.EXACT_ONE,
        version_id=UUID("00000000-0000-0000-0000-000000000099"),
        representative_count=40,
        query_class="factual_definition",
    )
    assert profile_id == HYBRID_DEFAULT_PROFILE_ID
    assert reason == "unfrozen_long_document_denied"


def test_review_apply_requires_locator_flag() -> None:
    """Locator-bound review cannot run without the inspection flag."""

    from scripts.review_pdf_eval_dataset import main as review_main

    fixture = (
        REPO_ROOT / "tests" / "fixtures" / "evaluation" / "private_pdf" / "generated_only.json"
    )
    assert review_main(["--input", str(fixture), "--apply", "--reviewer", "Nagdy"]) == 2


def test_seal_rejects_holdout_inside_repository() -> None:
    """Holdout custody cannot be written inside the git worktree."""

    from scripts.seal_pdf_eval_dataset import main as seal_main

    fixture = (
        REPO_ROOT / "tests" / "fixtures" / "evaluation" / "private_pdf" / "generated_only.json"
    )
    inside = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "evaluation"
        / "private_pdf"
        / "must-not-write-holdout.json"
    )
    assert (
        seal_main(
            [
                "--input",
                str(fixture),
                "--reviewer",
                "Nagdy",
                "--holdout-out",
                str(inside),
            ]
        )
        == 2
    )


def test_pdf_judge_rejects_synthetic_prompt_pin() -> None:
    """The PDF judge cannot be invoked with the synthetic eval_judge_v1 pin."""

    from smart_rag_core.gateways.openai_answer import (
        OpenAIAnswerError,
        execute_openai_pdf_eval_judge,
    )
    from smart_rag_core.query_answer.versions import (
        EVAL_JUDGE_MODEL_ID,
        EVAL_JUDGE_PROMPT_SHA256,
        EVAL_JUDGE_PROMPT_VERSION,
    )

    with pytest.raises(OpenAIAnswerError, match="eval_pdf_judge_version_mismatch"):
        execute_openai_pdf_eval_judge(
            api_key="sk-test",
            prompt_text="unused",
            prompt_sha256=EVAL_JUDGE_PROMPT_SHA256,
            prompt_version=EVAL_JUDGE_PROMPT_VERSION,
            model_id=EVAL_JUDGE_MODEL_ID,
            user_payload={},
            timeout_seconds=5.0,
        )


def test_manifest_hash_is_reproducible() -> None:
    """Git-safe manifests hash stably without question text."""

    first = _case(
        human_approved=True,
        generated_only=False,
        reviewer="reviewer",
        acl_actor_id="actor-1",
    )
    second = _case(
        human_approved=True,
        generated_only=False,
        reviewer="reviewer",
        acl_actor_id="actor-1",
    )
    assert manifest_hash((first,)) == manifest_hash((second,))


def test_seal_cli_rejects_generated_fixture() -> None:
    """The sealer rejects the committed generated-only fixture."""

    from scripts.seal_pdf_eval_dataset import main as seal_main

    fixture = (
        REPO_ROOT / "tests" / "fixtures" / "evaluation" / "private_pdf" / "generated_only.json"
    )
    assert seal_main(["--input", str(fixture)]) == 2


def test_holdout_eval_script_default_deny_does_not_open() -> None:
    """Holdout CLI stays closed without an immutable purpose token."""

    source = (REPO_ROOT / "scripts" / "eval_pdf_holdout.py").read_text(encoding="utf-8")
    assert "prompts/eval_judge_v1.md" not in source
    from scripts.eval_pdf_holdout import main as holdout_main

    assert holdout_main(["--labels", str(REPO_ROOT / "missing-holdout.json")]) == 2
