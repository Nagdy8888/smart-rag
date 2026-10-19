"""Post-verify rewrite keeps grounded titles and leaves exact answers alone."""

from __future__ import annotations

from types import SimpleNamespace

from smart_rag_agents.query.deps import QueryGraphDeps
from smart_rag_agents.query.nodes.organize import organize_answer_node
from smart_rag_core.query_answer.models import AnswerParagraph, AnswerPayload
from smart_rag_core.query_fusion.models import (
    FusionAlgorithm,
    FusionResult,
    PassageOrigin,
    ScoredPassage,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope


def _payload(text: str) -> AnswerPayload:
    """Build one company answer whose paragraph matches ``text``.

    Args:
        text: Verified prose.

    Returns:
        Payload with one supporting link.
    """

    return AnswerPayload(
        answer_text=text,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=text, link_ids=("link-1",)),
        ),
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
        status="complete",
    )


def _state(text: str) -> dict[str, object]:
    """Build graph state around one verified company answer.

    Args:
        text: Verified prose.

    Returns:
        Minimal organize-node state.
    """

    return {
        "status": "verified",
        "user_query": "How does the process run?",
        "remaining_model_calls": 2,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "answer": _payload(text).model_dump(mode="json"),
    }


class _Gateway:
    """Return one organized claim or a claim that adds a new word."""

    def __init__(self, text: str) -> None:
        """Store the claim body the provider will return.

        Args:
            text: Claim text, including newlines.
        """

        self.text = text
        self.calls = 0

    async def generate_answer(self, _request: object) -> SimpleNamespace:
        """Return a claims payload. No network.

        Args:
            _request: Ignored organize request.

        Returns:
            Object with ``payload`` and token counts.
        """

        self.calls += 1
        return SimpleNamespace(
            payload={
                "claims": [
                    {
                        "text": self.text,
                        "kind": "fact",
                        "citations": [
                            {
                                "source_id": "verified",
                                "span": "Alpha runs first.",
                                "source_ranges": [],
                            }
                        ],
                    }
                ],
                "conclusion": None,
                "status": "complete",
            },
            input_tokens=2,
            output_tokens=3,
        )


def test_organize_rewrites_several_sentences_and_keeps_the_link() -> None:
    """A grounded title replaces the pasted sentences."""

    verified = "Alpha runs first. Beta runs second."
    gateway = _Gateway("**Alpha**\nAlpha runs first, then Beta runs second.")
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert answer["answer_text"].startswith("**Alpha**")
    assert "Beta" in answer["answer_text"]
    assert gateway.calls == 1
    assert updated["remaining_model_calls"] == 1
    assert updated["prompt_tokens"] == 2


def test_organize_keeps_a_one_sentence_answer() -> None:
    """One sentence does not spend a model call."""

    gateway = _Gateway("**Alpha**\nAlpha runs first.")
    text = "Alpha runs first."
    updated = organize_answer_node(
        _state(text),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert answer["answer_text"] == text
    assert gateway.calls == 0


def test_organize_keeps_a_lowercase_rewording() -> None:
    """A titled paraphrase that adds no name stays."""

    verified = "Alpha runs first. Beta runs second."
    gateway = _Gateway(
        "**Alpha**\nAlpha executes first.\n**Beta**\nBeta then updates the stored step."
    )
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert answer["answer_text"].startswith("**Alpha**")
    assert "executes" in answer["answer_text"]


def test_organize_allows_a_joined_name_already_in_the_text() -> None:
    """Joining words that are already present is still grounded."""

    verified = "Alpha runs first. The Graph RAG step runs second."
    gateway = _Gateway("**Graph RAG**\nThe GraphRAG step runs after Alpha.")
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert "GraphRAG" in str(answer["answer_text"])


def test_organize_rewrites_prose_and_keeps_the_table() -> None:
    """A mixed answer is titled, and the pipe table stays exact."""

    table = "| Name | Note |\n| --- | --- |\n| Alpha | First |"
    verified = f"Alpha runs first. Beta runs second.\n{table}"
    gateway = _Gateway("**Alpha**\nAlpha runs first.\n- Beta runs second.")
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    text = str(answer["answer_text"])
    assert text.startswith("**Alpha**")
    assert table in text
    assert gateway.calls == 1


def _fusion(citation: str) -> dict[str, object]:
    """Build one fusion result that holds a single figure.

    Args:
        citation: Figure caption stored as evidence.

    Returns:
        JSON-ready fusion mapping.
    """

    return FusionResult(
        algorithm=FusionAlgorithm.NAIVE_UNION,
        config_hash="a" * 64,
        requested_route="composite",
        effective_route="composite",
        graph_discovered_only_ratio=0.0,
        evidence=(
            ScoredPassage(
                chunk_id="11111111-1111-1111-1111-111111111111",
                document_id="22222222-2222-2222-2222-222222222222",
                version_id="33333333-3333-3333-3333-333333333333",
                citation_text=citation,
                combined_score=1.0,
                origin=PassageOrigin.HYBRID,
                graph_discovered_only=False,
                content_kind="figure",
                figure_id="abc123",
            ),
        ),
    ).model_dump(mode="json")


def test_organize_inserts_a_figure_when_the_question_asks() -> None:
    """A figure question gets the image without rewriting one sentence."""

    state = _state("Alpha runs first.")
    state["user_query"] = "What does Figure 2-1 show?"
    state["fusion"] = _fusion("Figure 2-1. Orchestration sits in the center.")
    gateway = _Gateway("**Alpha**\nAlpha runs first.")
    updated = organize_answer_node(
        state,  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert "[[figure:abc123]]" in str(answer["answer_text"])
    assert gateway.calls == 0


def test_organize_inserts_a_figure_the_answer_already_uses() -> None:
    """A figure whose caption is already in the answer is shown."""

    state = _state("Orchestration coordinates every tool call. Planning comes next.")
    state["user_query"] = "How does coordination work?"
    state["fusion"] = _fusion("Orchestration coordinates every tool call in the diagram.")
    gateway = _Gateway("unused")
    updated = organize_answer_node(
        state,  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert "[[figure:abc123]]" in str(answer["answer_text"])
    assert gateway.calls == 1


def test_organize_leaves_an_unrelated_figure_out() -> None:
    """A retrieved figure that the answer does not use stays out."""

    state = _state("Alpha runs first. Beta runs second.")
    state["fusion"] = _fusion("Warehouse shelves stacked beside a loading dock.")
    gateway = _Gateway("**Alpha**\nAlpha runs first.\n- Beta runs second.")
    updated = organize_answer_node(
        state,  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert "[[figure:" not in str(answer["answer_text"])


def test_organize_puts_a_figure_mark_back() -> None:
    """The rewrite cannot drop a figure mark that was already verified."""

    verified = "Alpha runs first. Beta runs second.\n[[figure:abc123]]"
    gateway = _Gateway("**Alpha**\nAlpha runs first.\n- Beta runs second.")
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    assert "[[figure:abc123]]" in str(answer["answer_text"])


def test_organize_rejects_a_new_word() -> None:
    """A rewrite that adds a word becomes a titled list of the original sentences."""

    table = "| Name | Note |\n| --- | --- |\n| Alpha | First |"
    verified = f"Alpha runs first. Beta runs second.\n{table}\n[[figure:abc123]]"
    gateway = _Gateway("**Alpha**\nAlpha runs first with Quuxlight added.")
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    text = str(answer["answer_text"])
    assert "Quuxlight" not in text
    assert text.startswith("**Alpha runs first**")
    assert "- Alpha runs first." in text
    assert "- Beta runs second." in text
    assert table in text
    assert "[[figure:abc123]]" in text
    assert gateway.calls == 1


def test_organize_keeps_a_bare_fence_out_of_the_title() -> None:
    """A fence line stays a fence and is not turned into a heading."""

    verified = "```\ndef helper():\n    return 1"
    gateway = _Gateway("**Alpha**\nAlpha runs first with Quuxlight added.")
    updated = organize_answer_node(
        _state(verified),  # type: ignore[arg-type]
        QueryGraphDeps(model_gateway=gateway, organize_prompt_text="organize"),
    )
    answer = updated["answer"]
    assert isinstance(answer, dict)
    text = str(answer["answer_text"])
    assert "```" in text
    assert "def helper" in text
    assert "**```**" not in text
    assert gateway.calls == 0
