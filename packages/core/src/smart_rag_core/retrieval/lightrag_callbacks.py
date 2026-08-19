"""Counted LightRAG LLM, embedding, and rerank callbacks.

Every callback is accounted by kind and routed through the shared
``EmbeddingGateway`` / ``ModelGateway``. Vendor and SDK retries are not
added here; ``max_retries`` stays zero on provider adapters.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from smart_rag_core.gateways.embedding import EmbeddingGateway, EmbeddingRequest
from smart_rag_core.gateways.model import LightRagLlmRequest, ModelGateway
from smart_rag_core.ingestion.embeddings.policy import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from smart_rag_core.retrieval.graph import (
    LIGHTRAG_LLM_TIMEOUT_SECONDS,
    LIGHTRAG_PINNED_VERSION,
)


@dataclass
class CallbackCounts:
    """Mutable callback counters for qualification proofs.

    Attributes:
        keyword_extract: Keyword-role LLM calls.
        answer_generate: Query-role LLM calls.
        entity_extract: Extract-role LLM calls.
        embed: Embedding gateway batches.
        rerank: Rerank callback invocations.
        other: Unclassified LLM roles.
    """

    keyword_extract: int = 0
    answer_generate: int = 0
    entity_extract: int = 0
    embed: int = 0
    rerank: int = 0
    other: int = 0

    def snapshot(self) -> dict[str, int]:
        """Return a JSON-safe copy of current counters.

        Returns:
            Mapping of counter name to count.
        """

        return {
            "keyword_extract": self.keyword_extract,
            "answer_generate": self.answer_generate,
            "entity_extract": self.entity_extract,
            "embed": self.embed,
            "rerank": self.rerank,
            "other": self.other,
        }


@dataclass
class CountedLightRagCallbacks:
    """Instrument LightRAG callbacks without a second retry layer.

    Attributes:
        embedding_gateway: Shared embedding boundary.
        model_gateway: Shared model boundary.
        counts: Mutable counters updated on every callback.
        timeout_seconds: Per-callback timeout bound recorded for evidence.
        extract_gate: Optional event the extract callback waits on. Used only
            by cancellation qualification. ``None`` on production paths.
        pre_provider_hook: Optional synchronous guard invoked before every
            embedding or LLM provider call so Packet 3 can verify lock and
            lease without holding a transaction.
        ingest_job_id: Optional claimed LightRAG job id. When set, extract
            callbacks emit ``[graph] extract_batch`` count lines.
    """

    embedding_gateway: EmbeddingGateway
    model_gateway: ModelGateway
    counts: CallbackCounts = field(default_factory=CallbackCounts)
    timeout_seconds: float = LIGHTRAG_LLM_TIMEOUT_SECONDS
    extract_gate: asyncio.Event | None = None
    pre_provider_hook: Callable[[], None] | None = None
    ingest_job_id: str | None = None

    async def embedding_texts(self, texts: list[str]) -> np.ndarray:
        """Embed one batch through the shared gateway at the pinned dimension.

        Args:
            texts: Vendor embedding inputs.

        Returns:
            ``float32`` matrix with one row per input.

        Raises:
            ValueError: If ``texts`` is empty.

        Side Effects:
            Increments ``embed`` and performs one gateway embedding call.
        """

        if not texts:
            raise ValueError("lightrag_embedding_batch_empty")
        self._run_pre_provider_hook()
        request = EmbeddingRequest(
            operation_key=f"lightrag-embed-{LIGHTRAG_PINNED_VERSION}",
            inputs=tuple(texts),
            model=EMBEDDING_MODEL,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        response = await self.embedding_gateway.embed(request)
        self.counts.embed += 1
        return np.asarray(response.vectors, dtype=np.float32)

    async def extract_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **_kwargs: object,
    ) -> str:
        """Handle extract-role LLM calls and count them as entity extraction.

        Args:
            prompt: Vendor user prompt.
            system_prompt: Optional vendor system prompt.
            history_messages: Unused vendor history. Not parsed.
            **_kwargs: Ignored vendor extras including priority.

        Returns:
            Extract callback text from the model gateway. Live mode calls
            OpenAI; mock mode returns a frozen fixture.

        Side Effects:
            May wait on ``extract_gate`` so cancellation tests can bound
            ``ainsert`` without leaving an unbounded sleep. When
            ``ingest_job_id`` is set, emits one ``[graph] extract_batch``
            count line. Never logs prompt text.
        """

        del history_messages
        self._run_pre_provider_hook()
        gate = self.extract_gate
        if gate is not None:
            await gate.wait()
        self.counts.entity_extract += 1
        job_id = self.ingest_job_id
        if job_id is not None:
            from smart_rag_core.observability.ingest_progress import log_ingest_progress

            log_ingest_progress(
                "graph",
                "extract_batch",
                job_id,
                extract_calls=self.counts.entity_extract,
            )
        response = await self.model_gateway.generate_lightrag_llm(
            LightRagLlmRequest(
                role="extract",
                prompt=prompt,
                system_prompt=system_prompt or "",
                timeout_seconds=max(
                    1.0,
                    min(self.timeout_seconds, LIGHTRAG_LLM_TIMEOUT_SECONDS),
                ),
            )
        )
        return response.content

    async def keyword_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **_kwargs: object,
    ) -> str:
        """Handle keyword-role LLM calls.

        Precomputed keyword lists must keep this counter at zero.

        Args:
            prompt: Vendor user prompt.
            system_prompt: Optional vendor system prompt.
            history_messages: Unused vendor history.
            **_kwargs: Ignored vendor extras.

        Returns:
            Empty keyword JSON from the model gateway.
        """

        del history_messages
        self._run_pre_provider_hook()
        self.counts.keyword_extract += 1
        response = await self.model_gateway.generate_lightrag_llm(
            LightRagLlmRequest(
                role="keyword",
                prompt=prompt,
                system_prompt=system_prompt or "",
            )
        )
        return response.content

    async def query_llm(
        self,
        prompt: str,
        system_prompt: str | None = None,
        history_messages: list[dict[str, str]] | None = None,
        **_kwargs: object,
    ) -> str:
        """Handle query-role LLM calls.

        ``aquery_data`` with ``only_need_context`` semantics must keep this
        counter at zero.

        Args:
            prompt: Vendor user prompt.
            system_prompt: Optional vendor system prompt.
            history_messages: Unused vendor history.
            **_kwargs: Ignored vendor extras.

        Returns:
            Explicit non-answer fixture text.
        """

        del history_messages
        self._run_pre_provider_hook()
        self.counts.answer_generate += 1
        response = await self.model_gateway.generate_lightrag_llm(
            LightRagLlmRequest(
                role="query",
                prompt=prompt,
                system_prompt=system_prompt or "",
            )
        )
        return response.content

    async def rerank_model(
        self,
        *_args: object,
        **_kwargs: object,
    ) -> list[object]:
        """Count unexpected native rerank callbacks and fail closed.

        Args:
            *_args: Vendor rerank arguments. Unused.
            **_kwargs: Vendor rerank keyword arguments. Unused.

        Returns:
            Never returns on the qualification path.

        Raises:
            RuntimeError: Native rerank is disabled for Packet 1 qualification.
        """

        self.counts.rerank += 1
        raise RuntimeError("lightrag_native_rerank_not_qualified")

    def _run_pre_provider_hook(self) -> None:
        """Invoke the optional lock/lease guard before a provider call.

        Raises:
            Exception: Propagates whatever the hook raises, typically a
                writer-lock loss error from Packet 3.
        """

        hook = self.pre_provider_hook
        if hook is not None:
            hook()
