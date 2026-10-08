"""Unit tests for private company-Ask LangSmith dataset/experiment publish."""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from smart_rag_core.evaluation.company_ask_diagnosis import (
    DiagnosisSignals,
    RunUsageTotals,
)
from smart_rag_core.evaluation.company_ask_langsmith import (
    CompanyAskLangSmithError,
    assert_local_private_upload_permitted,
    dataset_name_for_gold,
    dual_metric_evaluators,
    example_id_for_question,
    gold_content_hash,
    plan_company_ask_langsmith_publish,
    publish_company_ask_experiment,
    sync_company_ask_dataset,
)
from smart_rag_core.evaluation.company_ask_regression import CompanyAskQuestion
from smart_rag_core.evaluation.dual_metric import RequiredFact


class FakeLangSmithClient:
    """In-memory LangSmith client for company-Ask publish tests."""

    def __init__(self) -> None:
        """Initialize empty dataset and example stores."""

        self.datasets: dict[str, dict[str, Any]] = {}
        self.examples: dict[str, dict[str, dict[str, Any]]] = {}
        self.evaluate_calls = 0
        self.last_evaluate: dict[str, Any] | None = None

    def has_dataset(self, *, dataset_name: str) -> bool:
        """Return whether the named dataset exists.

        Args:
            dataset_name: Dataset name.

        Returns:
            True when created.
        """

        return dataset_name in self.datasets

    def create_dataset(
        self,
        dataset_name: str,
        *,
        description: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> object:
        """Create one dataset.

        Args:
            dataset_name: Dataset name.
            description: Unused description.
            metadata: Identity metadata.

        Returns:
            Namespace with metadata.
        """

        del description
        self.datasets[dataset_name] = dict(metadata or {})
        self.examples.setdefault(dataset_name, {})
        return SimpleNamespace(metadata=self.datasets[dataset_name])

    def read_dataset(self, *, dataset_name: str) -> object:
        """Read one dataset.

        Args:
            dataset_name: Dataset name.

        Returns:
            Namespace with metadata.
        """

        return SimpleNamespace(metadata=self.datasets[dataset_name])

    def list_examples(self, *, dataset_name: str) -> Iterator[Any]:
        """List examples.

        Args:
            dataset_name: Dataset name.

        Yields:
            Example namespaces.
        """

        for example_id, payload in self.examples.get(dataset_name, {}).items():
            yield SimpleNamespace(
                id=example_id,
                metadata=payload["metadata"],
                inputs=payload["inputs"],
                outputs=payload["outputs"],
            )

    def create_examples(
        self,
        *,
        dataset_name: str,
        examples: Sequence[Mapping[str, Any]],
        max_concurrency: int = 1,
    ) -> object:
        """Create missing examples.

        Args:
            dataset_name: Dataset name.
            examples: Example payloads.
            max_concurrency: Must stay 1.

        Returns:
            None.
        """

        del max_concurrency
        bucket = self.examples.setdefault(dataset_name, {})
        for example in examples:
            example_id = str(example["id"])
            bucket[example_id] = {
                "inputs": dict(example["inputs"]),
                "outputs": dict(example["outputs"]),
                "metadata": dict(example["metadata"]),
            }
        return None

    def evaluate(
        self,
        target: Any,
        /,
        data: str | None = None,
        evaluators: Sequence[Any] | None = None,
        metadata: dict[str, Any] | None = None,
        experiment_prefix: str | None = None,
        description: str | None = None,
        max_concurrency: int | None = 0,
        num_repetitions: int = 1,
        blocking: bool = True,
        upload_results: bool = True,
        error_handling: str = "log",
    ) -> object:
        """Run evaluate against in-memory examples and attach feedback.

        Args:
            target: Target callable.
            data: Dataset name.
            evaluators: Dual-metric evaluators.
            metadata: Experiment metadata.
            experiment_prefix: Prefix.
            description: Unused.
            max_concurrency: Concurrency.
            num_repetitions: Repetitions.
            blocking: Unused.
            upload_results: Unused.
            error_handling: Unused.

        Returns:
            Namespace with experiment URL.
        """

        del description, blocking, upload_results, error_handling
        self.evaluate_calls += 1
        assert data is not None
        scores: list[dict[str, Any]] = []
        for example in self.list_examples(dataset_name=data):
            outputs = target(dict(example.inputs))
            run = SimpleNamespace(outputs=outputs)
            for evaluator in evaluators or ():
                scores.append(evaluator(run, example))
        self.last_evaluate = {
            "data": data,
            "metadata": dict(metadata or {}),
            "experiment_prefix": experiment_prefix,
            "max_concurrency": max_concurrency,
            "num_repetitions": num_repetitions,
            "scores": scores,
        }
        return SimpleNamespace(
            experiment_url="https://smith.langchain.com/o/demo/datasets/exp/1",
            url="https://smith.langchain.com/o/demo/datasets/exp/1",
        )


def _sample_questions() -> tuple[CompanyAskQuestion, ...]:
    """Return two synthetic gold questions for unit tests.

    Returns:
        Frozen company-Ask questions with synthetic phrases.
    """

    return (
        CompanyAskQuestion(
            question_id="syn-q1",
            prompt="What is the synthetic widget code?",
            facts=(
                RequiredFact(
                    fact_id="f1",
                    canonical_phrases=("widget-alpha",),
                    approved_aliases=("WA-1",),
                ),
            ),
            page=10,
            kind="text",
        ),
        CompanyAskQuestion(
            question_id="syn-q2",
            prompt="Name the synthetic process.",
            facts=(
                RequiredFact(
                    fact_id="f2",
                    canonical_phrases=("process bravo",),
                ),
            ),
            page=20,
            kind="text",
        ),
    )


def test_local_upload_gate_requires_opt_in_and_local_env() -> None:
    """Private LangSmith upload fails closed without local opt-in."""

    with pytest.raises(CompanyAskLangSmithError, match="upload_private_content"):
        assert_local_private_upload_permitted(
            app_env="local",
            upload_private_content=False,
        )
    with pytest.raises(CompanyAskLangSmithError, match="local_only"):
        assert_local_private_upload_permitted(
            app_env="staging",
            upload_private_content=True,
        )
    assert_local_private_upload_permitted(
        app_env="local",
        upload_private_content=True,
    )


def test_dataset_name_and_example_ids_are_stable() -> None:
    """Gold hash and example UUID5 identities stay stable across calls."""

    questions = _sample_questions()
    first_hash = gold_content_hash(questions)
    second_hash = gold_content_hash(questions)
    assert first_hash == second_hash
    assert (
        dataset_name_for_gold(questions) == f"smart-rag-company-ask-{first_hash[:12]}"
    )
    digest = first_hash
    assert example_id_for_question(
        "syn-q1", gold_content_hash=digest
    ) == example_id_for_question("syn-q1", gold_content_hash=digest)
    assert example_id_for_question(
        "syn-q1", gold_content_hash=digest
    ) != example_id_for_question("syn-q2", gold_content_hash=digest)
    assert example_id_for_question(
        "syn-q1", gold_content_hash=digest
    ) != example_id_for_question("syn-q1", gold_content_hash="0" * 64)


def test_plan_dry_run_has_no_network_side_effects() -> None:
    """Dry-run plan reports dataset identity without needing a client."""

    questions = _sample_questions()
    plan = plan_company_ask_langsmith_publish(
        questions=questions,
        project_name="smart-rag-company-ask-eval",
    )
    assert plan.dry_run is True
    assert plan.case_count == 2
    assert plan.dataset_name.startswith("smart-rag-company-ask-")
    assert plan.schema_version == "company-ask-langsmith-v1"


def test_sync_and_publish_create_experiment_with_dual_metric_feedback(
    tmp_path: Path,
) -> None:
    """Publish syncs examples and scores dual-metric feedback in evaluate."""

    questions = _sample_questions()
    client = FakeLangSmithClient()
    answer_rows = {
        "syn-q1": {
            "answer_text": "The code is widget-alpha.",
            "conversation_id": "c1",
            "run_id": "r1",
            "stages": {"fused_count": 2, "retrieval_empty": False},
        },
        "syn-q2": {
            "answer_text": "It is process bravo.",
            "conversation_id": "c2",
            "run_id": "r2",
            "stages": {"fused_count": 1, "retrieval_empty": False},
        },
    }
    summary_path = tmp_path / "summary.json"
    diagnosis = {
        "syn-q1": DiagnosisSignals(
            gold_page=10,
            gold_page_cited=True,
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=True,
            gold_page_in_selected=True,
            failure_bucket="pass",
            kind="text",
        ),
        "syn-q2": DiagnosisSignals(
            gold_page=20,
            gold_page_cited=False,
            gold_page_in_fused=True,
            gold_page_in_rerank_pool=True,
            gold_page_in_selected=True,
            failure_bucket="phrasing",
            kind="text",
        ),
    }
    summary = publish_company_ask_experiment(
        client,
        questions=questions,
        answer_rows=answer_rows,
        app_env="local",
        upload_private_content=True,
        summary_out=summary_path,
        diagnosis=diagnosis,
    )
    assert client.evaluate_calls == 1
    assert summary.case_count == 2
    assert summary.strict_pass == 2
    assert summary.grounded_fact_pass == 2
    assert summary.deadline_failures == 0
    assert summary.experiment_url is not None
    assert summary_path.is_file()
    assert client.last_evaluate is not None
    keys = {
        item["key"]
        for item in cast(list[dict[str, Any]], client.last_evaluate["scores"])
    }
    assert keys == {
        "strict_pass",
        "grounded_fact_pass",
        "fact_coverage",
        "no_deadline_failure",
        "gold_page_cited",
        "gold_in_fused",
        "failure_bucket",
        "estimated_cost_usd",
        "total_tokens",
    }
    usage = {
        "syn-q1": RunUsageTotals(
            input_tokens=100,
            output_tokens=20,
            total_tokens=120,
            total_cost_usd=Decimal("0.0015"),
            model_id="gpt-4o-mini",
            usage_kinds=("answer", "embedding"),
        ),
        "syn-q2": RunUsageTotals(
            input_tokens=80,
            output_tokens=10,
            total_tokens=90,
            total_cost_usd=Decimal("0.0010"),
            model_id="gpt-4o-mini",
            usage_kinds=("answer",),
        ),
    }
    # Re-publish with usage so cost feedback is populated.
    client2 = FakeLangSmithClient()
    summary2 = publish_company_ask_experiment(
        client2,
        questions=questions,
        answer_rows=answer_rows,
        app_env="local",
        upload_private_content=True,
        diagnosis=diagnosis,
        usage=usage,
    )
    assert summary2.total_cost_usd == pytest.approx(0.0025)
    assert summary2.total_tokens == 210
    assert client2.last_evaluate is not None
    by_key: dict[str, list[Any]] = {}
    for item in cast(list[dict[str, Any]], client2.last_evaluate["scores"]):
        by_key.setdefault(str(item["key"]), []).append(item)
    assert {item.get("value") for item in by_key["failure_bucket"]} == {
        "pass",
        "phrasing",
    }
    assert {item.get("score") for item in by_key["gold_page_cited"]} == {0.0, 1.0}
    assert {item.get("score") for item in by_key["gold_in_fused"]} == {1.0}
    assert {item.get("score") for item in by_key["estimated_cost_usd"]} == {
        0.0015,
        0.001,
    }
    assert {item.get("score") for item in by_key["total_tokens"]} == {120.0, 90.0}


def test_dataset_drift_fails_closed() -> None:
    """Changed gold content against an existing dataset name fails closed."""

    questions = _sample_questions()
    client = FakeLangSmithClient()
    name = sync_company_ask_dataset(client, questions)
    client.datasets[name]["gold_content_hash"] = "0" * 64
    with pytest.raises(CompanyAskLangSmithError, match="dataset_drift"):
        sync_company_ask_dataset(client, questions)


def test_dual_metric_evaluators_score_missed_answer() -> None:
    """Evaluators return zero strict pass when the answer misses gold phrases."""

    questions = _sample_questions()
    example = SimpleNamespace(
        outputs={
            "facts": [
                {
                    "id": "f1",
                    "canonical": ["widget-alpha"],
                    "aliases": [],
                }
            ]
        }
    )
    run = SimpleNamespace(
        outputs={
            "answer_text": "unrelated answer",
            "stages": {"fused_count": 1, "retrieval_empty": False},
            "diagnosis": {
                "gold_page_cited": False,
                "gold_page_in_fused": False,
                "failure_bucket": "retrieval_miss",
            },
        }
    )
    scored = {
        item["key"]: item
        for item in (fn(run, example) for fn in dual_metric_evaluators())
    }
    assert scored["strict_pass"]["score"] == 0.0
    assert scored["grounded_fact_pass"]["score"] == 0.0
    assert scored["fact_coverage"]["score"] == 0.0
    assert scored["no_deadline_failure"]["score"] == 1.0
    assert scored["gold_page_cited"]["score"] == 0.0
    assert scored["gold_in_fused"]["score"] == 0.0
    assert scored["failure_bucket"]["score"] == 0.0
    assert scored["failure_bucket"]["value"] == "retrieval_miss"
    assert scored["estimated_cost_usd"]["comment"] == "unknown"
    assert scored["total_tokens"]["comment"] == "unknown"
    del questions
