"""Process-lifetime immutable query-graph bindings."""

from __future__ import annotations

from dataclasses import dataclass

from smart_rag_core.query_routing.branches import (
    GraphRetrieveLike,
    HybridRetrieveLike,
    TableExecuteLike,
)


class QueryGraphRuntimeError(RuntimeError):
    """Live SSE cannot compile an unbound query graph.

    Attributes:
        reason: Stable machine-readable code. Never a secret or DSN.
    """

    def __init__(self, reason: str) -> None:
        """Store one fail-closed runtime reason.

        Args:
            reason: Short identifier for logs and SSE ``error.code``.
        """

        super().__init__(reason)
        self.reason = reason


@dataclass(slots=True)
class QueryGraphProcessBindings:
    """Process-reusable adapters. Per-run cancel and ``app_api`` connections stay off this object.

    Attributes:
        hybrid_retriever: DSN-based Hybrid retrieve. Channel threads open
            their own Postgres connections.
        model_gateway: Counted gateway. Mock mode is still a gateway.
        graph_retriever: Process LightRAG adapter, or None when unbound.
        table_executor: Structured-table path using ``app_api`` ACL.
        answer_prompt_text: Pinned ``answer_v2`` body.
        organize_prompt_text: Pinned ``organize_v1`` body.
        general_chat_prompt_text: Pinned ``general_chat_v1`` body.
        verifier_prompt_text: Pinned ``verifier_v1`` body.
        query_profile_prompt_text: Pinned ``query_profile_v1`` body.
        profile_model_id: Allow-listed profile model recorded on usage.
        supabase_dsn: Canonical Postgres URL for per-run ``app_api`` connections.
        web_search_enabled: ``WEB_SEARCH_ENABLED`` snapshot. Default false.
        web_search_configured: True when a non-empty Exa key is present.
        exa_search_gateway: Injected Exa REST client, or None.
        crawl_proxy_gateway: Injected crawl-proxy client, or None.
        web_critique_prompt_text: Pinned ``web_critique_v1`` body.
        web_answer_prompt_text: Pinned ``web_answer_v1`` body.
        model_input_max_chars: Existing ``MODEL_INPUT_MAX_CHARS`` bound.
    """

    hybrid_retriever: HybridRetrieveLike
    model_gateway: object
    graph_retriever: GraphRetrieveLike | None
    table_executor: TableExecuteLike | None
    answer_prompt_text: str
    general_chat_prompt_text: str
    verifier_prompt_text: str
    query_profile_prompt_text: str
    profile_model_id: str
    supabase_dsn: str
    web_search_enabled: bool = False
    web_search_configured: bool = False
    exa_search_gateway: object | None = None
    crawl_proxy_gateway: object | None = None
    web_critique_prompt_text: str = ""
    web_answer_prompt_text: str = ""
    model_input_max_chars: int = 32_768
    organize_prompt_text: str = ""
