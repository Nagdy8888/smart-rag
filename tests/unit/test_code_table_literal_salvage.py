"""Promote and salvage named code definitions and table bodies."""

from __future__ import annotations

from uuid import uuid4

from smart_rag_core.query_answer.generate_grounded import (
    salvage_named_code_definition,
    salvage_named_table_block,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope
from smart_rag_core.retrieval.rerank import (
    RerankPassage,
    literal_anchor_ask,
    named_code_definition_ids,
    named_table_captions,
    promote_named_code_definition_passages,
    promote_named_table_passages,
)
from smart_rag_core.retrieval.types import RetrievalCandidate

from tests.support.answer_verifier import (
    verifier_fusion,
    verifier_passage,
    verifier_uid,
)


def _passage(*, text: str) -> RerankPassage:
    """Build one synthetic rerank passage.

    Args:
        text: Canonical passage text.

    Returns:
        Passage wrapping a fresh candidate id.
    """

    candidate = RetrievalCandidate(
        chunk_id=uuid4(),
        document_id=uuid4(),
        version_id=uuid4(),
        channel_rank=1,
        channel_score=1.0,
    )
    return RerankPassage(
        candidate=candidate,
        raw_text=text,
        token_count=max(1, len(text.split())),
        channels=frozenset({"dense"}),
        excerpt=text,
    )


def _payload(text: str, *, chunk: str) -> AnswerPayload:
    """Build a one-claim answer citing ``chunk``.

    Args:
        text: Claim prose.
        chunk: Cited chunk id.

    Returns:
        Complete company answer payload.
    """

    return AnswerPayload(
        answer_text=text,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=text, link_ids=("claim-1",)),
        ),
        citations=(
            AnswerCitation(
                chunk_id=chunk,
                span=text[:40],
                paragraph_index=0,
                atomic_link_id="claim-1",
            ),
        ),
        atomic_links=(AtomicLink(link_id="claim-1", claim=text, chunk_ids=(chunk,)),),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_literal_anchor_ask_matches_reproduce_code_and_table() -> None:
    """Reproduce-code and reproduce-table asks are literal anchors."""

    assert literal_anchor_ask(
        "reproduce the cancel_order tool definition as a fenced Python code block"
    )
    assert literal_anchor_ask("reproduce Table 2-1 as a Markdown pipe table")
    assert named_code_definition_ids(
        "reproduce the cancel_order @tool function as a fenced code block"
    ) == ("cancel_order",)
    assert named_code_definition_ids(
        "reproduce the optimize_delivery @tool and the TOOLS list "
        "assignment as a fenced Python code block"
    ) == ("optimize_delivery",)
    assert named_table_captions("reproduce Table 2-1 as a Markdown pipe table") == (
        "Table 2-1",
    )
    assert literal_anchor_ask(
        "Show the Python function parse_invoice from the document."
    )
    assert named_code_definition_ids(
        "Show the Python function parse_invoice from the document."
    ) == ("parse_invoice",)
    assert not literal_anchor_ask("What does the document say about retry budgets?")


def test_promote_named_code_definition_prefers_def_over_invoke() -> None:
    """A cancel_order ask pins the definition, not a same-page invoke example."""

    invoke = _passage(
        text=(
            'example_order = {"order_id": "A12345"}\n'
            'result = graph.invoke({"order": example_order})\n'
            "cancel_order is called later"
        )
    )
    definition = _passage(
        text=(
            "@tool def cancel_order(order_id: str) -> str: "
            '"""Cancel an order that hasn\'t shipped.""" '
            'return f"Order {order_id} has been cancelled."'
        )
    )
    query = (
        "reproduce the cancel_order tool definition as a fenced Python "
        "code block (not a prose paraphrase)"
    )
    promoted = promote_named_code_definition_passages(
        (invoke,),
        query=query,
        pool=(invoke, definition),
        limit=12,
    )
    assert promoted[0].candidate.chunk_id == definition.candidate.chunk_id


def test_promote_named_code_definition_prefers_named_tool_over_sibling() -> None:
    """A coordinate_operations ask pins that def over a sibling tool page."""

    sibling = _passage(
        text=(
            "@tool def track_shipments(origin: str = None, **kwargs) -> str: "
            'return "shipment_tracking_updated"'
        )
    )
    gold = _passage(
        text=(
            "@tool def coordinate_operations(operation_type: str = None, "
            '**kwargs) -> str: return "operations_coordinated"'
        )
    )
    query = (
        "reproduce the coordinate_operations @tool definition as a "
        "fenced Python code block"
    )
    promoted = promote_named_code_definition_passages(
        (sibling,),
        query=query,
        pool=(sibling, gold),
        limit=12,
    )
    assert promoted[0].candidate.chunk_id == gold.candidate.chunk_id


def test_salvage_named_code_definition_replaces_wrong_neighbor() -> None:
    """Wrong invoke snippet is replaced when evidence holds the definition."""

    gold = (
        "@tool def cancel_order(order_id: str) -> str: "
        '"""Cancel an order that hasn\'t shipped.""" '
        'return f"Order {order_id} has been cancelled."'
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        'example_order = {"order_id": "A12345"} '
        'convo = [HumanMessage(content="Please cancel my order A12345.")]',
        chunk=verifier_uid(1),
    )
    salvaged = salvage_named_code_definition(
        payload,
        fusion,
        user_query=(
            "reproduce the cancel_order tool definition as a fenced Python code block"
        ),
    )
    assert "def cancel_order(order_id: str) -> str:" in salvaged.answer_text
    assert "Cancel an order that hasn't shipped." in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == verifier_uid(1)


def test_salvage_named_code_definition_replaces_partial_body() -> None:
    """A matching def line with the wrong body is still salvaged."""

    gold = (
        "@tool\ndef query_wolfram_alpha(expression: str) -> str:\n"
        '    """Query Wolfram Alpha."""\n\n'
        "    api_url = f'https://api.wolframalpha.com/v1/result?"
        "i={requests.utils.quote(expression)}"
        "&appid={YOUR_WOLFRAM_ALPHA_APP_ID}'\n"
        "    return requests.get(api_url).text\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "@tool def query_wolfram_alpha(expression: str) -> str: "
        "api_url = f'https://api.wolframalpha.com/v1/result?"
        "i={requests.utils.quote(expression)}"
        "&appid={WOLFRAM_ALPHA_APP_ID}'",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_named_code_definition(
        payload,
        fusion,
        user_query=(
            "reproduce the query_wolfram_alpha @tool definition as a "
            "fenced Python code block"
        ),
    )
    assert "YOUR_WOLFRAM_ALPHA_APP_ID" in salvaged.answer_text
    assert "\n\n" not in salvaged.paragraphs[0].text
    salvaged_span = salvaged.citations[0].span
    assert salvaged_span is not None
    assert salvaged_span in gold


def test_promote_named_table_prefers_caption_with_rows() -> None:
    """A Table 2-1 ask pins caption+rows over a prose intro without rows."""

    prose = _passage(
        text=(
            "In Table 2-1, a small selection of language models are shown "
            "along with their performance on MMLU."
        )
    )
    body = _passage(
        text=(
            "Table 2-1. Selected open weight models by performance and size\n"
            "Model Maintainer MMLU Parameters (billion)\n"
            "Llama 3.1 Instruct Turbo Meta 56.1 8 20 RTX 3090\n"
            "Gemma 2 Google 72.1 9 22.5 RTX 3090\n"
        )
    )
    query = (
        "reproduce Table 2-1 (Selected open weight models by performance "
        "and size) as a Markdown pipe table"
    )
    promoted = promote_named_table_passages(
        (prose,),
        query=query,
        pool=(prose, body),
        limit=12,
    )
    assert promoted[0].candidate.chunk_id == body.candidate.chunk_id


def test_salvage_named_table_block_replaces_header_only_prose() -> None:
    """Header/prose answers are replaced when evidence holds table rows."""

    gold = (
        "Table 2-1. Selected open weight models by performance and size\n"
        "Model Maintainer MMLU Parameters (billion)\n"
        "Llama 3.1 Instruct Turbo Meta 56.1 8 20 RTX 3090\n"
        "Gemma 2 Google 72.1 9 22.5 RTX 3090\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "model handles the most complex queries and a lightweight model "
        "handles routine tasks.\nModel Maintainer MMLU Parameters (billion)",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_named_table_block(
        payload,
        fusion,
        user_query=(
            "reproduce Table 2-1 as a Markdown pipe table with the model "
            "rows shown on that page"
        ),
    )
    assert "Table 2-1" in salvaged.answer_text
    assert "Llama 3.1 Instruct Turbo" in salvaged.answer_text
    assert "72.1" in salvaged.answer_text


def test_salvage_named_code_definition_stops_before_sibling_def() -> None:
    """Flattened evidence with a later def does not trail into the answer."""

    gold = (
        "@tool def cancel_order(order_id: str) -> str: "
        '"""Cancel an order that hasn\'t shipped.""" '
        'return f"Order {order_id} has been cancelled." '
        "# -- 2) The agent brain "
        "def call_model(state): msgs = state['messages']"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("wrong neighbor invoke text", chunk=verifier_uid(1))
    salvaged = salvage_named_code_definition(
        payload,
        fusion,
        user_query=(
            "reproduce the cancel_order tool definition as a fenced Python code block"
        ),
    )
    assert "def cancel_order(order_id: str) -> str:" in salvaged.answer_text
    assert "has been cancelled." in salvaged.answer_text
    assert "call_model" not in salvaged.answer_text
    assert "# -- 2)" not in salvaged.answer_text


def test_literal_gold_already_loaded_ignores_table_prose_intro() -> None:
    """Prose that only mentions Table N-M does not count as table gold loaded."""

    prose = _passage(
        text=(
            "In Table 2-1, a small selection of language models are shown "
            "along with their performance on MMLU."
        )
    )
    body = _passage(
        text=(
            "Table 2-1. Selected open weight models by performance and size\n"
            "Model Maintainer MMLU Parameters (billion)\n"
            "Llama 3.1 Instruct Turbo Meta 56.1 8 20 RTX 3090\n"
            "Gemma 2 Google 72.1 9 22.5 RTX 3090\n"
        )
    )
    query = "reproduce Table 2-1 as a Markdown pipe table"
    from smart_rag_core.retrieval.rerank import literal_gold_already_loaded

    assert literal_gold_already_loaded(query, (prose,)) is False
    assert literal_gold_already_loaded(query, (prose, body)) is True


def test_salvage_named_table_prefers_titled_body_over_prose_intro() -> None:
    """Prose intros lose to titled Table N-M. bodies with digit rows."""

    prose = (
        "In Table 2-1, a small selection of language models are shown "
        "along with their performance on the MMLU benchmark."
    )
    body = (
        "Table 2-1. Selected open weight models by performance and size\n"
        "Model Maintainer MMLU Parameters (billion)\n"
        "Llama 3.1 Instruct Turbo Meta 56.1 8 20 RTX 3090\n"
        "Gemma 2 Google 72.1 9 22.5 RTX 3090\n"
        "22 | Chapter 2: Designing Agent Systems\n"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text=prose, rank=1),
        verifier_passage(2, text=body, rank=2),
    )
    payload = _payload(prose, chunk=verifier_uid(1))
    salvaged = salvage_named_table_block(
        payload,
        fusion,
        user_query=(
            "reproduce Table 2-1 as a Markdown pipe table with the model "
            "rows shown on that page"
        ),
    )
    assert salvaged.answer_text.startswith("Table 2-1.")
    assert "Llama 3.1 Instruct Turbo" in salvaged.answer_text
    assert "72.1" in salvaged.answer_text
    assert "a small selection" not in salvaged.answer_text
    assert "Chapter 2" not in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == verifier_uid(2)


def test_salvage_named_table_keeps_later_rows_after_capitalized_line() -> None:
    """Capitalized OCR rows must not truncate later table body rows."""

    body = (
        "Table 10-2. Comparison of monitoring and observability stacks\n\n"
        "Stack Key strength Best for Trade-off (versus Grafana) "
        "Grafana + Loki/Tempo Composability and visualization "
        "Enterprise ops More components to manage\n\n"
        "ELK Stack Advanced search/analytics Large-scale logs "
        "Higher resource use\n\n"
        "SigNoz Unified and lightweight Startups/ML teams "
        "Less extensible\n\n"
        "Langfuse Foundation model/agent-specific evals "
        "Semantic monitoring Narrower infra coverage\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=body, rank=1))
    payload = _payload("wrong prose", chunk=verifier_uid(1))
    salvaged = salvage_named_table_block(
        payload,
        fusion,
        user_query=("reproduce Table 10-2 as a Markdown pipe table (not a prose list)"),
    )
    assert "Table 10-2." in salvaged.answer_text
    assert "Grafana + Loki/Tempo" in salvaged.answer_text
    assert "Langfuse" in salvaged.answer_text
    assert "SigNoz" in salvaged.answer_text


def test_salvage_named_table_prefers_titled_page_over_continuation() -> None:
    """A denser continuation page that only back-references Table N-M loses."""

    continuation = (
        "Model Maintainer MMLU Parameters (billion)\n"
        "NeMo Mistral 65.3 12 24 RTX 3090\n"
        "Phi-3 Microsoft 77.5 14.7 29.4 A100\n"
        "Qwen1.5 Alibaba 74.4 32 60.11 A100\n"
        "Llama 3 Meta 79.3 70 160 4xA100\n"
        "As you'll see in Table 2-1, models up to roughly 14 billion "
        "parameters can be run on a single consumer-grade GPU such as "
        "NVIDIA's RTX 3090 with 24 GB of video RAM. Above this threshold "
        "you will probably want a server-grade GPU such as NVIDIA's A100, "
        "which comes in 40 GB and 80 GB varieties."
    )
    titled = (
        "Table 2-1. Selected open weight models by performance and size\n"
        "Model Maintainer MMLU Parameters (billion)\n"
        "Llama 3.1 Instruct Turbo Meta 56.1 8 20 RTX 3090\n"
        "Gemma 2 Google 72.1 9 22.5 RTX 3090\n"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text=continuation, rank=1),
        verifier_passage(2, text=titled, rank=2),
    )
    payload = _payload(
        "Insufficient authorized evidence.",
        chunk=verifier_uid(1),
    )
    payload = payload.model_copy(update={"status": "refused"})
    salvaged = salvage_named_table_block(
        payload,
        fusion,
        user_query=(
            "reproduce Table 2-1 as a Markdown pipe table with the model "
            "rows shown on that page"
        ),
    )
    assert salvaged.status == "complete"
    assert salvaged.answer_text.startswith("Table 2-1.")
    assert "Llama 3.1 Instruct Turbo" in salvaged.answer_text
    assert "Gemma 2" in salvaged.answer_text
    assert "72.1" in salvaged.answer_text
    assert "14 billion" not in salvaged.answer_text
    assert salvaged.citations[0].chunk_id == verifier_uid(2)


def test_salvage_named_code_trims_trailing_sibling_when_already_present() -> None:
    """A correct def that still trails a sibling def is re-salvaged clean."""

    gold = (
        "@tool def cancel_order(order_id: str) -> str: "
        '"""Cancel an order that hasn\'t shipped.""" '
        'return f"Order {order_id} has been cancelled."'
    )
    evidence = (
        gold
        + " # -- 2) The agent brain "
        + "def call_model(state): msgs = state['messages']"
    )
    dirty = (
        gold
        + ' # -- 2) The agent brain def call_model(state): msgs = state["messages"]'
    )
    fusion = verifier_fusion(verifier_passage(1, text=evidence, rank=1))
    payload = _payload(dirty, chunk=verifier_uid(1))
    salvaged = salvage_named_code_definition(
        payload,
        fusion,
        user_query=(
            "reproduce the cancel_order tool definition as a fenced Python code block"
        ),
    )
    assert "def cancel_order(order_id: str) -> str:" in salvaged.answer_text
    assert "has been cancelled." in salvaged.answer_text
    assert "call_model" not in salvaged.answer_text
    assert "# -- 2)" not in salvaged.answer_text


def test_salvage_cites_a_definition_already_on_screen() -> None:
    """A shown definition with no citations still cites its chunk."""

    gold = "def parse_invoice(path):\n    return path\n"
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    visible = gold.strip()
    payload = AnswerPayload(
        answer_text=visible,
        paragraphs=(
            AnswerParagraph(paragraph_index=0, text=visible, link_ids=("claim-1",)),
        ),
        citations=(),
        atomic_links=(
            AtomicLink(
                link_id="claim-1",
                claim="Shown definition.",
                chunk_ids=(verifier_uid(1),),
            ),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )
    salvaged = salvage_named_code_definition(
        payload,
        fusion,
        user_query="Show the Python function parse_invoice from the document.",
    )
    assert salvaged.answer_text == visible
    assert len(salvaged.citations) == 1
    assert salvaged.citations[0].chunk_id == verifier_uid(1)
    span = salvaged.citations[0].span
    assert span is not None
    assert span in gold
