"""Extractive salvage for exact-wording paraphrases on selected evidence."""

from __future__ import annotations

from smart_rag_core.query_answer.generate_grounded import (
    distinctive_query_names,
    generate_grounded_answer,
    salvage_query_literal_extractive,
)
from smart_rag_core.query_answer.models import (
    AnswerCitation,
    AnswerParagraph,
    AnswerPayload,
    AtomicLink,
)
from smart_rag_core.query_routing.knowledge_scope import KnowledgeScope

from tests.support.answer_verifier import verifier_fusion, verifier_passage, verifier_uid


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
        atomic_links=(
            AtomicLink(link_id="claim-1", claim=text, chunk_ids=(chunk,)),
        ),
        status="complete",
        answer_origin=KnowledgeScope.COMPANY_DOCUMENTS,
    )


def test_book_title_tokens_are_not_query_name_anchors() -> None:
    """Prompts that name the book must not treat title words as anchors."""

    names = distinctive_query_names(
        "In the company document Building Applications with AI Agents, "
        "what exact phrase pairs Tempo with its role?"
    )
    assert "Tempo" in names
    assert "Building" not in names
    assert "Applications" not in names
    assert "Agents" not in names


def test_exact_wording_paraphrase_is_replaced_when_anchor_missing() -> None:
    """Exact-wording asks salvage when the answer omits the named anchor."""

    gold = (
        "Tempo For distributed traces\n"
        "Grafana For visualization, alerts, and dashboards\n"
        "We'll walk through how to integrate each of these with a "
        "LangGraph-based agent system."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "The observability stack lists a distributed tracing backend "
        "alongside Grafana for dashboards.",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "in the observability stack list, what exact phrase pairs Tempo "
            "with its role? Use only that document. Give the exact wording, "
            "name, or code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "Tempo For distributed traces" in salvaged.answer_text
    assert salvaged.status == "complete"
    assert salvaged.citations


def test_exact_wording_keeps_substantial_extractive_answer() -> None:
    """Do not clobber an answer that already is the extractive span."""

    gold = (
        "Tempo For distributed traces\n"
        "Grafana For visualization, alerts, and dashboards\n"
        "We'll walk through how to integrate each of these with a "
        "LangGraph-based agent system."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(
        "Tempo For distributed traces\n"
        "Grafana For visualization, alerts, and dashboards",
        chunk=verifier_uid(1),
    )
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "in the observability stack list, what exact phrase pairs Tempo "
            "with its role? Use only that document. Give the exact wording, "
            "name, or code fragment from the page."
        ),
    )
    assert salvaged is payload


def test_short_name_only_answer_expands_to_body_literal() -> None:
    """Exact-ask name-only answers salvage the body line with the asked filter."""

    gold = (
        "SigNoz\n"
        "SigNoz is a unified, OTel-native platform that combines metrics, "
        "traces, and logs in a single tool.\n"
        "Example: trace a multistep agent flow, filtering by "
        "token_usage > 1000 to spot inefficiencies, with built-in evals."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("SigNoz", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "what token_usage filter example does the SigNoz section give "
            "for spotting inefficiencies? Give the exact wording, name, or "
            "code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "token_usage > 1000" in salvaged.answer_text


def test_heading_label_paraphrase_salvages_exact_phrase() -> None:
    """Exact-ask heading answers that omit the gold label are replaced."""

    gold = (
        "Deploy in phases\n"
        "Start with a small pilot cohort before full production deployment "
        "so operators can calibrate autonomy and monitoring."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("roll out gradually", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "what phased rollout heading does the book recommend starting "
            "with before full deployment? Give the exact wording, name, or "
            "code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "Deploy in phases" in salvaged.answer_text


def test_glued_heading_label_salvages_deploy_in_phases() -> None:
    """PDF lines that glue the heading to body still release the label."""

    gold = (
        "Real-world testing ensures an agent's readiness for deployment by "
        "validating its performance under real-life conditions. This process "
        "involves a phased rollout, continuous monitoring of key metrics.\n"
        "Evaluating performance under load Stress the agent with peak traffic "
        "before promoting a release candidate.\n"
        "Deploy in phases Roll out the agent in stages, starting with "
        "small-scale testing in a limited environment before scaling up to "
        "full deployment."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("Real-World Testing", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "what rollout approach does real-world testing recommend starting "
            "with before full deployment? Give the exact wording, name, or "
            "code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert salvaged.answer_text.strip().startswith("Deploy in phases")
    assert "Deploy in phases" in salvaged.answer_text


def test_already_extractive_answer_is_left_alone() -> None:
    """Salvage is a no-op when the answer already covers the evidence span."""

    gold = (
        "Tempo For distributed traces\n"
        "Grafana For visualization, alerts, and dashboards\n"
        "We'll walk through how to integrate each of these with a "
        "LangGraph-based agent system that closes the observation loop."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload(gold, chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "Give the exact wording from the page for the Tempo observability "
            "stack line in Building Applications with AI Agents."
        ),
    )
    assert salvaged is payload


def test_after_anchor_toc_salvages_next_section_title() -> None:
    """TOC asks naming prior titles salvage the next compact section label."""

    gold = (
        "12 LangGraph                                                    "
        "13 AutoGen                                                      "
        "14 CrewAI                                                       "
        "15 Knowledge and Memory                                         "
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("Knowledge and Memory", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "what agentic framework section title appears in the Table of "
            "Contents immediately after LangGraph and AutoGen? Give the "
            "exact wording, name, or code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "CrewAI" in salvaged.answer_text


def test_locator_host_line_salvages_platform_name() -> None:
    """Asks that name a sibling host salvage the line holding both hosts."""

    gold = (
        "Browse searchable MCP server directories such as mcp.so and "
        "Glama.ai when wiring plug-in tools into an open-source stack."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("Plug-In Tools", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "which platform does the plug-in ecosystem section say aggregates "
            "searchable MCP servers alongside Glama.ai? Give the exact "
            "wording, name, or code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "mcp.so" in salvaged.answer_text


def test_long_paragraph_centers_span_on_host_locators() -> None:
    """Long intro paragraphs still release the buried host pair."""

    gold = (
        "In addition to the offerings from major platforms, there is a rapidly "
        "growing ecosystem of tools that can be incorporated into open source "
        "foundation models. This ecosystem provides a wealth of resources for "
        "developers looking to enhance their systems with community-driven "
        "plug-in tools and enhancements, driven by the collective efforts of "
        "researchers, developers, and enthusiasts. Platforms like Glama.ai, "
        "and mcp.so aggregate large numbers of MCP servers, making them "
        "searchable and discoverable, ranging from simple utilities to complex, "
        "stateful services."
    )
    # Pad so a naive head trim drops the hosts.
    gold = ("Community catalogs continue to expand each quarter. " * 8) + gold
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("Plug-In Tools", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "which platform does the plug-in ecosystem section say aggregates "
            "searchable MCP servers alongside Glama.ai? Give the exact "
            "wording, name, or code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "mcp.so" in salvaged.answer_text
    assert "Glama.ai" in salvaged.answer_text


def test_code_shape_prefers_def_chunk_over_neighbor_prose() -> None:
    """Constructor asks prefer the chunk that holds the def line."""

    prose = (
        "In the supply chain example, an actor agent generates reorder plans "
        "and a critic evaluates for feasibility before approval."
    )
    code = (
        "def construct_actor_critic_graph():\n"
        "    graph = StateGraph(AgentState)\n"
        "    return graph.compile()\n"
    )
    fusion = verifier_fusion(
        verifier_passage(1, text=prose, rank=1),
        verifier_passage(2, text=code, rank=2),
    )
    payload = _payload("Actor-Critic Approaches", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "in the actor-critic supply chain snippet, what graph "
            "constructor function is defined? Give the exact wording, name, "
            "or code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "def construct_actor_critic_graph():" in salvaged.answer_text


def test_code_shape_salvages_def_with_indicator_arg() -> None:
    """Mock-tool asks salvage the def line that takes the asked argument."""

    gold = (
        "DSPy excels at automating prompt refinement by compiling optimized "
        "prompts from a set of examples.\n"
        "def lookup_threat_intel(indicator: str) -> str:\n"
        "    return catalog.get(indicator, 'unknown')\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("Prompt and Tool Refinement", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "in the DSPy SOC optimization snippet, what mock tool function "
            "takes an indicator string? Give the exact wording, name, or "
            "code fragment from the page."
        ),
    )
    assert salvaged is not payload
    assert "def lookup_threat_intel(indicator: str) -> str:" in salvaged.answer_text


def test_snake_locator_salvages_otel_span_name() -> None:
    """Span-name asks that mention call_tool_node salvage the tracer line."""

    gold = (
        "OTel Instrumentation\n"
        "with tracer.start_as_current_span(\"call_tool\") as span:\n"
        "    return call_tool_node(state)\n"
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))
    payload = _payload("OTel Instrumentation", chunk=verifier_uid(1))
    salvaged = salvage_query_literal_extractive(
        payload,
        fusion,
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "in the OTel LangGraph example, what span name wraps "
            "call_tool_node? Give the exact wording, name, or code fragment "
            "from the page."
        ),
    )
    assert salvaged is not payload
    assert 'tracer.start_as_current_span("call_tool"' in salvaged.answer_text


def test_generate_grounded_runs_extractive_salvage_on_paraphrase() -> None:
    """generate_grounded_answer applies extractive salvage after a paraphrase."""

    gold = (
        "SigNoz is a unified, OTel-native platform that combines metrics, "
        "traces, and logs in a single tool, suitable for streamlined "
        "extensions of basic monitoring setups:\n"
        "Example: trace a multistep agent flow, filtering by "
        "token_usage > 1000 to spot inefficiencies."
    )
    fusion = verifier_fusion(verifier_passage(1, text=gold, rank=1))

    def _paraphrase(
        _records: str,
        _fusion: object,
        _tables: object,
    ) -> AnswerPayload:
        """Return a paraphrased complete answer.

        Args:
            _records: Unused assembled records.
            _fusion: Unused fusion.
            _tables: Unused tables.

        Returns:
            Complete paraphrased payload.
        """

        return _payload(
            "The monitoring platform unifies metrics and traces for agents.",
            chunk=verifier_uid(1),
        )

    payload = generate_grounded_answer(
        fusion=fusion,
        tables=(),
        user_query=(
            "In the company document Building Applications with AI Agents, "
            "what token_usage filter example does the SigNoz section give? "
            "Give the exact wording, name, or code fragment from the page."
        ),
        caller=_paraphrase,
    )
    assert "token_usage > 1000" in payload.answer_text
    assert payload.status == "complete"
