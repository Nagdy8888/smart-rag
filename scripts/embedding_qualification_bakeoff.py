#!/usr/bin/env python3
"""Run the Phase 2 embedding qualification bakeoff on the frozen slice_v1 corpus.

Live OpenAI calls embed every document and query for three required candidates,
compute Recall@10, MRR, and nDCG@10 per language bucket, and write raw metrics to
``docs/evaluation/embedding_qualification_raw.json``.
"""

from __future__ import annotations

import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from smart_rag_core.settings.base import SharedSettings, load_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
SLICE_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "embedding_qualification" / "slice_v1.json"
)
OUTPUT_PATH = REPO_ROOT / "docs" / "evaluation" / "embedding_qualification_raw.json"
MAX_WORKERS = 4
EMBED_BATCH_SIZE = 16

# Published list prices (USD per 1M input tokens) from OpenAI pricing docs,
# retrieved 2026-08-12: https://openai.com/api/pricing/
PRICING_USD_PER_MILLION_TOKENS = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
}


@dataclass(frozen=True)
class EmbeddingCandidate:
    """Describe one embedding model configuration under qualification.

    Attributes:
        candidate_id: Stable identifier used in reports.
        model: OpenAI embedding model name.
        dimensions: Requested output dimensionality.
    """

    candidate_id: str
    model: str
    dimensions: int


@dataclass(frozen=True)
class RankedQueryMetrics:
    """Aggregate ranking metrics for one query set.

    Attributes:
        recall_at_10: Mean Recall@10 across queries.
        mrr: Mean reciprocal rank of the first relevant document.
        ndcg_at_10: Mean nDCG@10 across queries.
        query_count: Number of evaluated queries in the bucket.
    """

    recall_at_10: float
    mrr: float
    ndcg_at_10: float
    query_count: int


CANDIDATES: tuple[EmbeddingCandidate, ...] = (
    EmbeddingCandidate(
        "text-embedding-3-small-default", "text-embedding-3-small", 1536
    ),
    EmbeddingCandidate("text-embedding-3-large-1536", "text-embedding-3-large", 1536),
    EmbeddingCandidate("text-embedding-3-large-1024", "text-embedding-3-large", 1024),
)


def load_slice() -> dict[str, Any]:
    """Load the frozen qualification slice fixture.

    Returns:
        Parsed JSON mapping with ``documents`` and ``queries`` lists.
    """

    return json.loads(SLICE_PATH.read_text(encoding="utf-8"))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity between two equal-length vectors.

    Args:
        left: First embedding vector.
        right: Second embedding vector.

    Returns:
        Cosine similarity in ``[-1, 1]``; ``0.0`` when either vector has zero norm.
    """

    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


def recall_at_k(relevant_ids: set[str], ranked_ids: list[str], *, k: int = 10) -> float:
    """Compute Recall@K for one query ranking.

    Args:
        relevant_ids: Ground-truth relevant document identifiers.
        ranked_ids: Retrieved identifiers ordered by descending similarity.
        k: Cutoff rank.

    Returns:
        Fraction of relevant documents found in the top ``k`` ranks.
    """

    if not relevant_ids:
        return 0.0
    top_k = set(ranked_ids[:k])
    return len(relevant_ids & top_k) / len(relevant_ids)


def reciprocal_rank(relevant_ids: set[str], ranked_ids: list[str]) -> float:
    """Compute reciprocal rank for one query ranking.

    Args:
        relevant_ids: Ground-truth relevant document identifiers.
        ranked_ids: Retrieved identifiers ordered by descending similarity.

    Returns:
        ``1/rank`` of the first relevant hit, or ``0.0`` when none appear.
    """

    for index, doc_id in enumerate(ranked_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / index
    return 0.0


def ndcg_at_k(relevant_ids: set[str], ranked_ids: list[str], *, k: int = 10) -> float:
    """Compute nDCG@K with binary relevance.

    Args:
        relevant_ids: Ground-truth relevant document identifiers.
        ranked_ids: Retrieved identifiers ordered by descending similarity.
        k: Cutoff rank.

    Returns:
        Normalized discounted cumulative gain at ``k``.
    """

    def dcg(ids: list[str]) -> float:
        """Compute binary discounted cumulative gain at the enclosing cutoff.

        Args:
            ids: Ranked document identifiers.

        Returns:
            Discounted gain for relevant identifiers in the top ``k``.
        """

        score = 0.0
        for index, doc_id in enumerate(ids[:k], start=1):
            if doc_id in relevant_ids:
                score += 1.0 / math.log2(index + 1)
        return score

    ideal = dcg(sorted(relevant_ids, key=str))
    if ideal == 0.0:
        return 0.0
    return dcg(ranked_ids) / ideal


def rank_documents(
    query_vector: list[float],
    doc_vectors: dict[str, list[float]],
) -> list[str]:
    """Rank document identifiers by cosine similarity to one query vector.

    Args:
        query_vector: Query embedding.
        doc_vectors: Document identifier to embedding mapping.

    Returns:
        Document identifiers sorted by descending similarity.
    """

    scored = [
        (doc_id, cosine_similarity(query_vector, vector))
        for doc_id, vector in doc_vectors.items()
    ]
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [doc_id for doc_id, _score in scored]


def evaluate_bucket(
    queries: list[dict[str, Any]],
    query_vectors: dict[str, list[float]],
    doc_vectors: dict[str, list[float]],
) -> RankedQueryMetrics:
    """Compute ranking metrics for one query bucket.

    Args:
        queries: Query records containing ``id`` and ``relevant_ids``.
        query_vectors: Query identifier to embedding mapping.
        doc_vectors: Document identifier to embedding mapping.

    Returns:
        Mean Recall@10, MRR, and nDCG@10 for the bucket.
    """

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for query in queries:
        query_id = str(query["id"])
        relevant = {str(item) for item in query["relevant_ids"]}
        ranked = rank_documents(query_vectors[query_id], doc_vectors)
        recalls.append(recall_at_k(relevant, ranked, k=10))
        reciprocal_ranks.append(reciprocal_rank(relevant, ranked))
        ndcgs.append(ndcg_at_k(relevant, ranked, k=10))
    count = len(queries)
    if count == 0:
        return RankedQueryMetrics(0.0, 0.0, 0.0, 0)
    return RankedQueryMetrics(
        recall_at_10=sum(recalls) / count,
        mrr=sum(reciprocal_ranks) / count,
        ndcg_at_10=sum(ndcgs) / count,
        query_count=count,
    )


def embed_texts(
    client: OpenAI,
    candidate: EmbeddingCandidate,
    texts: list[str],
) -> tuple[list[list[float]], int, int, float]:
    """Embed a bounded text list with limited parallel batching.

    Args:
        client: Configured OpenAI client.
        candidate: Model configuration under test.
        texts: Input strings to embed.

    Returns:
        Tuple of vectors, total prompt tokens, total latency milliseconds, and
        batch count.
    """

    vectors: list[list[float]] = [[] for _ in texts]
    total_tokens = 0
    total_latency_ms = 0.0
    batches = [
        (start, texts[start : start + EMBED_BATCH_SIZE])
        for start in range(0, len(texts), EMBED_BATCH_SIZE)
    ]

    def embed_batch(
        batch_index: int, batch_texts: list[str]
    ) -> tuple[int, list[list[float]], int, float]:
        """Embed one batch and return its index and vectors."""

        started = time.perf_counter()
        if candidate.model == "text-embedding-3-large":
            response = client.embeddings.create(
                model=candidate.model,
                input=batch_texts,
                dimensions=candidate.dimensions,
            )
        else:
            response = client.embeddings.create(
                model=candidate.model,
                input=batch_texts,
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        if not response.model.startswith(candidate.model):
            raise RuntimeError(
                f"Silent model substitution: requested {candidate.model}, got {response.model}"
            )
        ordered = sorted(response.data, key=lambda item: item.index)
        batch_vectors = [item.embedding for item in ordered]
        tokens = response.usage.total_tokens if response.usage else 0
        return batch_index, batch_vectors, tokens, elapsed_ms

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(embed_batch, index, batch_texts)
            for index, (_, batch_texts) in enumerate(batches)
        ]
        for future in as_completed(futures):
            batch_index, batch_vectors, tokens, elapsed_ms = future.result()
            start = batch_index * EMBED_BATCH_SIZE
            for offset, vector in enumerate(batch_vectors):
                vectors[start + offset] = vector
            total_tokens += tokens
            total_latency_ms += elapsed_ms

    return vectors, total_tokens, int(total_latency_ms), len(batches)


def estimate_usd_cost(model: str, total_tokens: int) -> float:
    """Estimate embedding spend using published list prices.

    Args:
        model: OpenAI embedding model name.
        total_tokens: Aggregate prompt tokens consumed.

    Returns:
        Approximate USD cost for the run.
    """

    rate = PRICING_USD_PER_MILLION_TOKENS[model]
    return (total_tokens / 1_000_000) * rate


def run_bakeoff(client: OpenAI, slice_data: dict[str, Any]) -> dict[str, Any]:
    """Execute the bakeoff for every candidate and language bucket.

    Args:
        client: Configured OpenAI client.
        slice_data: Parsed qualification slice fixture.

    Returns:
        JSON-serializable report mapping.
    """

    documents = slice_data["documents"]
    queries = slice_data["queries"]
    doc_ids = [str(doc["id"]) for doc in documents]
    doc_texts = [str(doc["text"]) for doc in documents]
    query_ids = [str(query["id"]) for query in queries]
    query_texts = [str(query["text"]) for query in queries]

    report_candidates: list[dict[str, Any]] = []
    for candidate in CANDIDATES:
        doc_vectors_list, doc_tokens, doc_latency_ms, doc_batches = embed_texts(
            client,
            candidate,
            doc_texts,
        )
        query_vectors_list, query_tokens, query_latency_ms, query_batches = embed_texts(
            client,
            candidate,
            query_texts,
        )
        doc_vectors = dict(zip(doc_ids, doc_vectors_list, strict=True))
        query_vectors = dict(zip(query_ids, query_vectors_list, strict=True))
        total_tokens = doc_tokens + query_tokens

        buckets = {
            "ar": [query for query in queries if query["lang"] == "ar"],
            "mixed": [query for query in queries if query["lang"] == "mixed"],
            "en": [query for query in queries if query["lang"] == "en"],
            "all": queries,
        }
        bucket_metrics: dict[str, Any] = {}
        for bucket_name, bucket_queries in buckets.items():
            metrics = evaluate_bucket(bucket_queries, query_vectors, doc_vectors)
            bucket_metrics[bucket_name] = {
                "recall_at_10": metrics.recall_at_10,
                "mrr": metrics.mrr,
                "ndcg_at_10": metrics.ndcg_at_10,
                "query_count": metrics.query_count,
            }

        report_candidates.append(
            {
                "candidate_id": candidate.candidate_id,
                "model": candidate.model,
                "dimensions": candidate.dimensions,
                "metrics_by_language": bucket_metrics,
                "latency_ms": {
                    "documents": doc_latency_ms,
                    "queries": query_latency_ms,
                    "total": doc_latency_ms + query_latency_ms,
                },
                "usage_tokens": {
                    "documents": doc_tokens,
                    "queries": query_tokens,
                    "total": total_tokens,
                },
                "estimated_usd": estimate_usd_cost(candidate.model, total_tokens),
                "pricing_source": "https://openai.com/api/pricing/ (2026-08-12 list rates)",
                "batching": {
                    "max_workers": MAX_WORKERS,
                    "embed_batch_size": EMBED_BATCH_SIZE,
                    "document_batches": doc_batches,
                    "query_batches": query_batches,
                },
            }
        )

    return {
        "slice_id": slice_data.get("slice_id"),
        "documents": len(documents),
        "queries": len(queries),
        "candidates": report_candidates,
    }


def print_summary(report: dict[str, Any]) -> None:
    """Print a human-readable summary of bakeoff metrics.

    Args:
        report: JSON-serializable bakeoff report.
    """

    print(f"Embedding qualification bakeoff — slice {report.get('slice_id')}")
    for candidate in report["candidates"]:
        print(
            f"\n{candidate['candidate_id']} "
            f"({candidate['model']} dim={candidate['dimensions']})"
        )
        print(
            f"  tokens={candidate['usage_tokens']['total']} "
            f"latency_ms={candidate['latency_ms']['total']} "
            f"usd~={candidate['estimated_usd']:.6f}"
        )
        for bucket, metrics in candidate["metrics_by_language"].items():
            print(
                f"  [{bucket}] R@10={metrics['recall_at_10']:.3f} "
                f"MRR={metrics['mrr']:.3f} nDCG@10={metrics['ndcg_at_10']:.3f} "
                f"(n={metrics['query_count']})"
            )


def main() -> int:
    """Run the bakeoff CLI and write raw JSON metrics.

    Returns:
        Process exit code ``0`` on success, ``1`` when prerequisites are missing.
    """

    settings = load_settings(SharedSettings)
    if settings.mock_model_mode:
        print(
            "MOCK_MODEL_MODE=true; set MOCK_MODEL_MODE=false for live bakeoff.",
            file=sys.stderr,
        )
        return 1
    if settings.openai_api_key is None:
        print("OPENAI_API_KEY is required for live bakeoff.", file=sys.stderr)
        return 1

    slice_data = load_slice()
    client = OpenAI(api_key=settings.openai_api_key.get_secret_value())
    report = run_bakeoff(client, slice_data)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print_summary(report)
    print(f"\nWrote {OUTPUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
