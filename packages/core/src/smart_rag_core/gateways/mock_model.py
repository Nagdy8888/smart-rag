"""Deterministic mock adapter. No sockets, retrieval, or provider clients."""

from __future__ import annotations

import re

from smart_rag_core.conversations.title import mock_conversation_title_payload
from smart_rag_core.gateways.model_types import (
    AnswerModelRequest,
    AnswerModelResponse,
    ConversationTitleModelRequest,
    ConversationTitleModelResponse,
    EvalJudgeModelRequest,
    EvalJudgeModelResponse,
    GeneralChatModelRequest,
    GeneralChatModelResponse,
    LightRagLlmRequest,
    LightRagLlmResponse,
    ModelRequest,
    ModelResponse,
    QueryProfileModelRequest,
    QueryProfileModelResponse,
    RerankModelRequest,
    RerankModelResponse,
    VerifierModelRequest,
    VerifierModelResponse,
    WebAnswerModelRequest,
    WebAnswerModelResponse,
    mock_lightrag_llm_content,
    reject_oversize_model_input,
    string_tuple,
)
from smart_rag_core.query_answer.models import AtomicLink
from smart_rag_core.query_answer.paragraphs import exact_source_span
from smart_rag_core.query_answer.verifier import mock_verifier_payload
from smart_rag_core.query_answer.versions import (
    ANSWER_PROMPT_SHA256,
    ANSWER_PROMPT_VERSION,
    CONVERSATION_TITLE_PROMPT_SHA256,
    CONVERSATION_TITLE_PROMPT_VERSION,
    EVAL_JUDGE_PROMPT_SHA256,
    EVAL_JUDGE_PROMPT_VERSION,
    GENERAL_CHAT_PROMPT_SHA256,
    GENERAL_CHAT_PROMPT_VERSION,
    MAX_ANSWER_PARAGRAPHS,
    MAX_VERIFIER_LINKS,
    VERIFIER_PROMPT_SHA256,
    VERIFIER_PROMPT_VERSION,
    WEB_ANSWER_PROMPT_SHA256,
    WEB_ANSWER_PROMPT_VERSION,
)
from smart_rag_core.query_profile.models import ModelInferredProfile
from smart_rag_core.query_profile.versions import (
    PROFILE_PROMPT_SHA256,
    PROFILE_PROMPT_VERSION,
)
from smart_rag_core.query_routing.knowledge_scope import mock_profile_knowledge_scope
from smart_rag_core.retrieval.rerank_labels import rerank_labels
from smart_rag_core.retrieval.rerank_versions import (
    RERANK_PROMPT_SHA256,
    RERANK_PROMPT_VERSION,
)


class MockModelAdapter:
    """Frozen adapter that performs no provider or retrieval work."""

    def __init__(self, *, fixture_id: str, max_input_chars: int) -> None:
        """Initialize deterministic fixture metadata and input bound.

        Args:
            fixture_id: Validated frozen fixture identifier.
            max_input_chars: Maximum accepted prompt length.
        """

        self._fixture_id = fixture_id
        self._max_input_chars = max_input_chars

    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Return an honest frozen fixture without opening a network socket.

        Args:
            request: Foundation probe request.

        Returns:
            Deterministic fixture response that explicitly denies retrieval.

        Raises:
            ValueError: If the request exceeds the deployable input bound.

        Side Effects:
            None. No network, provider, persistence, or retrieval calls occur.
        """

        reject_oversize_model_input(request.prompt, self._max_input_chars)
        return ModelResponse(
            mode="mock",
            content=(
                "Frozen model fixture only; no retrieval, provider call, or "
                "business answer was performed."
            ),
            fixture_provenance=f"fixture://smart-rag/mock-model/{self._fixture_id}",
            retrieval_performed=False,
        )

    async def generate_query_profile(
        self, request: QueryProfileModelRequest
    ) -> QueryProfileModelResponse:
        """Return a deterministic scope payload without a provider call.

        Args:
            request: Structured profile request.

        Returns:
            Mock payload with schema-valid scope fields. No DNS or OpenAI
            client is constructed.

        Raises:
            ValueError: If the query exceeds the input bound or the prompt
                hash does not match the pinned prompt.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        joined = request.query + request.recent_memory
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        if (
            request.prompt_version != PROFILE_PROMPT_VERSION
            or request.prompt_sha256 != PROFILE_PROMPT_SHA256
        ):
            raise ValueError("profile_prompt_version_mismatch")
        scope, confidence = mock_profile_knowledge_scope(request.query)
        payload: dict[str, object] = {
            "rewrite": None,
            "query_type": None,
            "subquestions": [],
            "variants": [],
            "hl_keywords": [],
            "ll_keywords": [],
            "retrieval_profile_id": None,
            "metadata_filters": [],
            "confidence": confidence,
            "relationship_intent": None,
            "knowledge_scope": scope.value,
            "knowledge_scope_confidence": confidence,
            "requested_sources": [],
        }
        return QueryProfileModelResponse(
            mode="mock",
            payload=payload,
            request_id=f"mock-profile-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
            inferred=ModelInferredProfile(confidence=confidence),
            fixture_provenance=f"fixture://smart-rag/mock-model/{self._fixture_id}",
            retrieval_performed=False,
        )

    async def generate_rerank(self, request: RerankModelRequest) -> RerankModelResponse:
        """Return identity rankings without a provider call.

        Args:
            request: Structured rerank request.

        Returns:
            Mock payload that preserves fused order.

        Raises:
            ValueError: If versions, lengths, or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != RERANK_PROMPT_VERSION
            or request.prompt_sha256 != RERANK_PROMPT_SHA256
        ):
            raise ValueError("rerank_prompt_version_mismatch")
        if len(request.candidate_ids) != len(request.excerpts):
            raise ValueError("rerank_excerpt_alignment")
        joined = request.query + "".join(request.excerpts)
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        labels = rerank_labels(len(request.candidate_ids))
        return RerankModelResponse(
            mode="mock",
            payload={
                "status": "complete",
                "ranking": list(labels),
                "support": {
                    label: 1.0 if index == 0 else 0.5
                    for index, label in enumerate(labels)
                },
            },
            request_id=f"mock-rerank-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_answer(self, request: AnswerModelRequest) -> AnswerModelResponse:
        """Return a fixture answer citing only supplied IDs. No network.

        Args:
            request: Structured answer request.

        Returns:
            Mock payload citing supplied chunk and table IDs.

        Raises:
            ValueError: If versions or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != ANSWER_PROMPT_VERSION
            or request.prompt_sha256 != ANSWER_PROMPT_SHA256
        ):
            raise ValueError("answer_prompt_version_mismatch")
        joined = request.query + request.source_records
        reject_oversize_model_input(joined, self._max_input_chars)
        sources = _parse_untrusted_sources(request.source_records)
        fallback_span = next(
            (
                exact_source_span(body)
                for kind, body, _ranges in sources.values()
                if kind != "structured-table" and exact_source_span(body)
            ),
            "",
        )
        paragraphs: list[dict[str, object]] = []
        citations: list[dict[str, object]] = []
        table_citations: list[dict[str, object]] = []
        links: list[dict[str, object]] = []
        for index, chunk_id in enumerate(request.chunk_ids, start=1):
            if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
                break
            if len(links) >= MAX_VERIFIER_LINKS:
                break
            record = sources.get(chunk_id)
            if record is not None and record[0] == "structured-table":
                continue
            span = exact_source_span(record[1]) if record is not None else fallback_span
            if not span:
                continue
            paragraph_index = len(paragraphs)
            link_id = f"link-{index}"
            paragraphs.append(
                {
                    "paragraph_index": paragraph_index,
                    "text": span[:4000],
                    "link_ids": [link_id],
                }
            )
            citations.append(
                {
                    "chunk_id": chunk_id,
                    "table_id": None,
                    "span": span,
                    "source_ranges": [],
                    "inference": False,
                    "atomic_link_id": link_id,
                    "paragraph_index": paragraph_index,
                }
            )
            links.append(
                {
                    "link_id": link_id,
                    "claim": f"Canonical passage {chunk_id}",
                    "chunk_ids": [chunk_id],
                    "table_id": None,
                    "source_ranges": [],
                    "kind": "fact",
                    "priority": index,
                }
            )
        for index, table_id in enumerate(request.table_ids, start=1):
            if len(paragraphs) >= MAX_ANSWER_PARAGRAPHS:
                break
            if len(links) >= MAX_VERIFIER_LINKS:
                break
            record = sources.get(table_id)
            ranges = record[2] if record is not None else ()
            if not ranges:
                continue
            body = exact_source_span(record[1]) if record is not None else ""
            if not body:
                body = f"Deterministic table {table_id}"
            paragraph_index = len(paragraphs)
            link_id = f"table-{index}"
            paragraphs.append(
                {
                    "paragraph_index": paragraph_index,
                    "text": body[:4000],
                    "link_ids": [link_id],
                }
            )
            table_citations.append(
                {
                    "chunk_id": None,
                    "table_id": table_id,
                    "span": None,
                    "source_ranges": list(ranges),
                    "inference": False,
                    "atomic_link_id": link_id,
                    "paragraph_index": paragraph_index,
                }
            )
            links.append(
                {
                    "link_id": link_id,
                    "claim": f"Canonical table {table_id}",
                    "chunk_ids": [],
                    "table_id": table_id,
                    "source_ranges": list(ranges),
                    "kind": "fact",
                    "priority": 100 + index,
                }
            )
        payload: dict[str, object] = {
            "paragraphs": paragraphs,
            "citations": citations,
            "atomic_links": links,
            "composed_conclusion": None,
            "table_citations": table_citations,
            "status": "complete" if paragraphs else "refused",
            "refused_links": [],
        }
        return AnswerModelResponse(
            mode="mock",
            payload=payload,
            request_id=f"mock-answer-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_web_answer(
        self, request: WebAnswerModelRequest
    ) -> WebAnswerModelResponse:
        """Return a fixture Web answer citing only supplied source IDs.

        Args:
            request: Structured Web-answer request.

        Returns:
            Mock payload with ``answer_text``, ``web_citations``, and
            ``atomic_links``.

        Raises:
            ValueError: If versions or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != WEB_ANSWER_PROMPT_VERSION
            or request.prompt_sha256 != WEB_ANSWER_PROMPT_SHA256
        ):
            raise ValueError("web_answer_prompt_version_mismatch")
        joined = request.query + request.source_records
        reject_oversize_model_input(joined, self._max_input_chars)
        web_citations: list[dict[str, object]] = []
        links: list[dict[str, object]] = []
        sentences: list[str] = []
        for index, source_id in enumerate(request.web_source_ids, start=1):
            if len(web_citations) >= MAX_ANSWER_PARAGRAPHS:
                break
            if source_id not in request.source_records:
                continue
            marker = f"id={source_id}"
            start = request.source_records.find(marker)
            span = f"Public web excerpt for {source_id}"[:180]
            if start >= 0:
                snippet = request.source_records[start : start + 400]
                for line in snippet.splitlines():
                    cleaned = line.strip()
                    if (
                        cleaned
                        and not cleaned.startswith("<<")
                        and not cleaned.startswith("title=")
                        and not cleaned.startswith("url_")
                    ):
                        span = cleaned[:180]
                        break
            link_id = f"web-{index}"
            web_citations.append({"web_source_id": source_id, "span": span})
            links.append(
                {
                    "link_id": link_id,
                    "claim": span[:200],
                    "web_source_ids": [source_id],
                }
            )
            sentences.append(span)
        text = " ".join(sentences)[:4000]
        return WebAnswerModelResponse(
            mode="mock",
            payload={
                "answer_text": text or "Insufficient public web evidence.",
                "status": "complete" if web_citations else "refused",
                "web_citations": web_citations,
                "atomic_links": links,
            },
            request_id=f"mock-web-answer-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_general_chat(
        self, request: GeneralChatModelRequest
    ) -> GeneralChatModelResponse:
        """Return a fixture general-chat answer. No network or retrieval.

        Args:
            request: Structured general-chat request.

        Returns:
            Mock payload with ``answer_text`` and ``status`` only.

        Raises:
            ValueError: If versions or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != GENERAL_CHAT_PROMPT_VERSION
            or request.prompt_sha256 != GENERAL_CHAT_PROMPT_SHA256
        ):
            raise ValueError("general_chat_prompt_version_mismatch")
        joined = request.query + request.recent_memory
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        from smart_rag_core.query_answer.generate import mock_general_chat_payload

        fixture = mock_general_chat_payload(
            request.query,
            recent_memory=request.recent_memory,
            knowledge_scope=request.knowledge_scope,
        )
        return GeneralChatModelResponse(
            mode="mock",
            payload={
                "answer_text": fixture.answer_text,
                "status": fixture.status,
            },
            request_id=f"mock-general-chat-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_conversation_title(
        self, request: ConversationTitleModelRequest
    ) -> ConversationTitleModelResponse:
        """Return a fixture session title. No network or retrieval.

        Args:
            request: Structured title request.

        Returns:
            Mock payload with ``title`` only.

        Raises:
            ValueError: If versions or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != CONVERSATION_TITLE_PROMPT_VERSION
            or request.prompt_sha256 != CONVERSATION_TITLE_PROMPT_SHA256
        ):
            raise ValueError("conversation_title_prompt_version_mismatch")
        joined = request.user_excerpt + request.assistant_excerpt
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        return ConversationTitleModelResponse(
            mode="mock",
            payload=mock_conversation_title_payload(request.user_excerpt),
            request_id=f"mock-conversation-title-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_verifier(
        self, request: VerifierModelRequest
    ) -> VerifierModelResponse:
        """Return identity-support verifier verdicts without a network call.

        Args:
            request: Structured verifier request.

        Returns:
            Mock payload covering at most six links.

        Raises:
            ValueError: If versions, batch size, or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != VERIFIER_PROMPT_VERSION
            or request.prompt_sha256 != VERIFIER_PROMPT_SHA256
        ):
            raise ValueError("verifier_prompt_version_mismatch")
        if len(request.links) > 6:
            raise ValueError("verifier_batch_cap")
        if len(request.source_records) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        links = tuple(
            AtomicLink(
                link_id=str(item.get("link_id") or f"link-{index}"),
                claim=str(item.get("claim") or "claim"),
                chunk_ids=string_tuple(item.get("chunk_ids")),
                table_id=(
                    str(item["table_id"]) if item.get("table_id") is not None else None
                ),
                source_ranges=string_tuple(item.get("source_ranges")),
                kind="inference_link"
                if item.get("kind") == "inference_link"
                else "fact",
            )
            for index, item in enumerate(request.links, start=1)
        )
        verdicts = mock_verifier_payload(links)
        return VerifierModelResponse(
            mode="mock",
            payload=verdicts.model_dump(mode="json"),
            request_id=f"mock-verifier-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_eval_judge(
        self, request: EvalJudgeModelRequest
    ) -> EvalJudgeModelResponse:
        """Return a fixture judge payload without a network call.

        Args:
            request: Structured judge request.

        Returns:
            Mock payload with unit scores and a short rationale.

        Raises:
            ValueError: If versions or the input bound fail.

        Side Effects:
            None. No network, retrieval, or tool calls.
        """

        if (
            request.prompt_version != EVAL_JUDGE_PROMPT_VERSION
            or request.prompt_sha256 != EVAL_JUDGE_PROMPT_SHA256
        ):
            raise ValueError("eval_judge_prompt_version_mismatch")
        joined = (
            request.question + request.answer_text + "".join(request.acceptable_answers)
        )
        if len(joined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        payload: dict[str, object] = {
            "correctness": 1.0,
            "groundedness": 1.0,
            "refusal_quality": 1.0,
            "rationale": "Mock judge fixture for synthetic development cases.",
        }
        return EvalJudgeModelResponse(
            mode="mock",
            payload=payload,
            request_id=f"mock-eval-judge-{self._fixture_id}",
            input_tokens=0,
            output_tokens=0,
        )

    async def generate_lightrag_llm(
        self, request: LightRagLlmRequest
    ) -> LightRagLlmResponse:
        """Return a bounded synthetic LightRAG callback without a network call.

        Args:
            request: LightRAG callback request.

        Returns:
            Role-specific mock payload. ``extract`` returns the vendor tuple
            format. ``keyword`` returns empty keyword JSON. ``query`` refuses
            to answer. No retrieval is performed.

        Raises:
            ValueError: If combined prompt text exceeds the input bound.

        Side Effects:
            None. No network, provider, or retrieval calls occur.
        """

        combined = request.system_prompt + request.prompt
        if len(combined) > self._max_input_chars:
            raise ValueError(
                f"Model input exceeds configured {self._max_input_chars}-character bound"
            )
        return LightRagLlmResponse(
            mode="mock",
            content=mock_lightrag_llm_content(request.role),
            fixture_provenance=(
                f"fixture://smart-rag/mock-lightrag-llm/{self._fixture_id}"
            ),
            retrieval_performed=False,
        )


_SOURCE_BLOCK = re.compile(
    r'<<untrusted-source id="(?P<id>[^"]+)"(?P<header>[^>]*)>>\s*'
    r"(?P<body>.*?)\s*</untrusted-source>",
    re.DOTALL,
)
_KIND_ATTR = re.compile(r'kind="([^"]*)"')
_RANGES_ATTR = re.compile(r'ranges="([^"]*)"')


def _parse_untrusted_sources(
    source_records: str,
) -> dict[str, tuple[str, str, tuple[str, ...]]]:
    """Parse delimited source records into id, kind, body, and table ranges.

    Args:
        source_records: Concatenated ``<<untrusted-source>>`` blocks.

    Returns:
        Mapping of source id to ``(kind, body, ranges)``. Missing ``kind``
        is treated as a canonical passage so compact fixtures still parse.
    """

    parsed: dict[str, tuple[str, str, tuple[str, ...]]] = {}
    for match in _SOURCE_BLOCK.finditer(source_records):
        header = match.group("header")
        kind_match = _KIND_ATTR.search(header)
        kind = kind_match.group(1) if kind_match is not None else "canonical-passage"
        ranges_match = _RANGES_ATTR.search(header)
        ranges = (
            tuple(
                item.strip()
                for item in ranges_match.group(1).split(",")
                if item.strip()
            )
            if ranges_match is not None
            else ()
        )
        parsed[match.group("id")] = (kind, match.group("body"), ranges)
    return parsed
