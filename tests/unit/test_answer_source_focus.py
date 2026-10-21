"""Question coverage affects presentation without altering fitted evidence."""

from smart_rag_core.query_answer.assembly import assemble_source_records
from smart_rag_core.query_answer.source_focus import prioritize_answer_sources
from smart_rag_core.query_fusion.models import FusionResult

from tests.support.answer_verifier import verified_answer_state, verifier_passage


def test_narrow_process_evidence_precedes_a_neighboring_role_taxonomy() -> None:
    """All records survive; the original process words select the first one."""
    unrelated = verifier_passage(1, text="Roles for a widget team: editor, reviewer.")
    relevant = verifier_passage(
        2, text="Production monitoring responsibilities: team A owns retries."
    )
    original = FusionResult.model_validate(verified_answer_state()["fusion"])
    original = original.model_copy(update={"evidence": (unrelated, relevant)})
    focused = prioritize_answer_sources(
        original, "Which production monitoring responsibilities belong to each team?"
    )
    assert focused.evidence == (relevant, unrelated)
    assert original.evidence == (unrelated, relevant)
    before = assemble_source_records(original, ())
    after = assemble_source_records(focused, ())
    assert len(before) == len(after)
    assert set(before.split("\n\n")) == set(after.split("\n\n"))


def test_equal_coverage_keeps_fitted_order() -> None:
    """No random tie breaking or rank mutation is introduced."""
    original = FusionResult.model_validate(verified_answer_state()["fusion"])
    assert prioritize_answer_sources(original, "unmatched topic") is original


def test_arabic_question_can_focus_english_human_responsibility_evidence() -> None:
    """Cross-language presentation cannot silently score every record as zero."""
    unrelated = verifier_passage(3, text="Agent deployment scope: team and enterprise.")
    relevant = verifier_passage(
        4, text="Human collaboration: role responsibilities change as people delegate."
    )
    original = FusionResult.model_validate(verified_answer_state()["fusion"])
    original = original.model_copy(update={"evidence": (unrelated, relevant)})
    focused = prioritize_answer_sources(
        original, "كيف تتغير أدوار البشر ومسؤولياتهم عندما يتعاونون مع الوكلاء؟"
    )
    assert focused.evidence == (relevant, unrelated)
    assert {p.chunk_id: p for p in focused.evidence} == {
        p.chunk_id: p for p in original.evidence
    }


def test_arabic_source_terms_remain_eligible_without_gloss_matches() -> None:
    """Arabic records retain literal normalized matching as well as glosses."""
    unrelated = verifier_passage(5, text="Other unrelated evidence.")
    relevant = verifier_passage(6, text="توزيع صلاحيات المستخدمين في النظام")
    original = FusionResult.model_validate(verified_answer_state()["fusion"])
    original = original.model_copy(update={"evidence": (unrelated, relevant)})
    focused = prioritize_answer_sources(original, "اشرح توزيع صلاحيات المستخدمين")
    assert focused.evidence == (relevant, unrelated)


def test_matching_section_breaks_equal_body_coverage_ties() -> None:
    """Long neighboring sections may mention all terms only in passing."""
    generic = verifier_passage(
        7, text="Human responsibilities and roles include review."
    )
    generic = generic.model_copy(
        update={"section_path": ("Organizational deployment",)}
    )
    specific = verifier_passage(8, text=generic.citation_text)
    specific = specific.model_copy(update={"section_path": ("Human roles",)})
    original = FusionResult.model_validate(verified_answer_state()["fusion"])
    original = original.model_copy(update={"evidence": (generic, specific)})
    focused = prioritize_answer_sources(
        original, "Explain human responsibilities and roles"
    )
    assert focused.evidence == (specific, generic)
