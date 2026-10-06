"""Word-for-word support override for verifier rejections."""

from __future__ import annotations

from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
    VerifierLinkVerdict,
    VerifierPayload,
)
from smart_rag_core.query_answer.verifier import (
    apply_verifier_payload,
    run_verifier_batch,
    verbatim_key,
    verbatim_supported_link_ids,
)
from smart_rag_core.query_fusion.models import FusionResult
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage

CODE_CHUNK = "def load_rows(path):\n    return [row for row in read(path)]"
PROSE_CHUNK = "The cache keeps 128 entries per worker."
CODE_CLAIM = (
    "```python\ndef load_rows(path):\n    return [row for row in read(path)]\n```"
)


def _payload(
    claims: tuple[str, str],
    *,
    table_id: str | None = None,
) -> tuple[AnswerPayload, FusionResult]:
    """Build a two-paragraph answer citing the code and prose chunks.

    Args:
        claims: Claim text for links ``l1`` (code chunk) and ``l2`` (prose).
        table_id: Optional table id set on link ``l2``.

    Returns:
        Answer payload and its fusion evidence.
    """

    fusion = verifier_fusion(
        verifier_passage(1, text=CODE_CHUNK),
        verifier_passage(2, text=PROSE_CHUNK, rank=2),
    )
    ids = tuple(item.chunk_id for item in fusion.evidence)
    payload = AnswerPayload(
        paragraphs=tuple(
            AnswerParagraph(
                paragraph_index=index, text=claim, link_ids=(f"l{index + 1}",)
            )
            for index, claim in enumerate(claims)
        ),
        citations=tuple(
            AnswerCitation(
                chunk_id=ids[index],
                span=claim,
                paragraph_index=index,
                atomic_link_id=f"l{index + 1}",
            )
            for index, claim in enumerate(claims)
        ),
        atomic_links=(
            AtomicLink(
                link_id="l1",
                claim=claims[0],
                chunk_ids=(ids[0],),
                kind="fact",
                priority=1,
            ),
            AtomicLink(
                link_id="l2",
                claim=claims[1],
                chunk_ids=(ids[1],),
                table_id=table_id,
                kind="fact",
                priority=2,
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    return payload, fusion


def _reject_all(links: tuple[AtomicLink, ...]) -> VerifierPayload:
    """Return a verifier batch that rejects every link.

    Args:
        links: Links selected for verification.

    Returns:
        Verifier payload with every verdict unsupported.
    """

    return VerifierPayload(
        link_verdicts=tuple(
            VerifierLinkVerdict(
                link_id=item.link_id, supported=False, reason="unsupported_link"
            )
            for item in links
        )
    )


def test_verbatim_key_drops_shape_markup() -> None:
    """Fences, table rules, pipes, entities, and quotes are normalized."""

    assert verbatim_key("```python\nA  b\n```") == "a b"
    assert verbatim_key("| A | B |\n|---|---|\n| 1 | 2 |") == "a b 1 2"
    assert verbatim_key("&lt;x&gt; \u201cq\u201d") == '<x> "q"'


def test_literal_claims_are_supported() -> None:
    """A fenced code copy and an exact sentence both count as verbatim."""

    payload, fusion = _payload((CODE_CLAIM, PROSE_CHUNK))
    assert verbatim_supported_link_ids(payload, fusion) == frozenset({"l1", "l2"})


def test_changed_value_is_not_supported() -> None:
    """A claim with a different number is not a literal copy."""

    payload, fusion = _payload(
        (CODE_CLAIM, "The cache keeps 256 entries per worker.")
    )
    assert verbatim_supported_link_ids(payload, fusion) == frozenset({"l1"})


def test_short_claim_is_never_verbatim() -> None:
    """A claim shorter than the minimum cannot bypass the verifier."""

    payload, fusion = _payload((CODE_CLAIM, "128 entries"))
    assert "l2" not in verbatim_supported_link_ids(payload, fusion)


def test_table_value_link_is_not_eligible() -> None:
    """Table-value links keep their verifier verdict."""

    payload, fusion = _payload((CODE_CLAIM, PROSE_CHUNK), table_id="t1")
    assert "l2" not in verbatim_supported_link_ids(payload, fusion)


def test_rejection_ignored_only_for_verbatim_links() -> None:
    """The verbatim link survives; the changed claim is still dropped."""

    payload, fusion = _payload(
        (CODE_CLAIM, "The cache keeps 256 entries per worker.")
    )
    updated = apply_verifier_payload(
        payload,
        _reject_all(payload.atomic_links),
        verbatim_ids=verbatim_supported_link_ids(payload, fusion),
    )
    assert tuple(item.link_id for item in updated.atomic_links) == ("l1",)
    assert "256" not in updated.answer_text
    assert updated.status != "refused"


def test_run_batch_applies_override_with_fusion() -> None:
    """With fusion, a full rejection of literal claims keeps both links."""

    payload, fusion = _payload((CODE_CLAIM, PROSE_CHUNK))
    updated, calls, omitted = run_verifier_batch(
        payload, caller=_reject_all, already_called=0, fusion=fusion
    )
    assert calls == 1
    assert omitted == ()
    assert tuple(item.link_id for item in updated.atomic_links) == ("l1", "l2")


def test_run_batch_without_fusion_keeps_old_behavior() -> None:
    """Without fusion, every rejected link is dropped as before."""

    payload, _fusion = _payload((CODE_CLAIM, PROSE_CHUNK))
    updated, _calls, _omitted = run_verifier_batch(
        payload, caller=_reject_all, already_called=0
    )
    assert updated.status == "refused"
    assert updated.atomic_links == ()
