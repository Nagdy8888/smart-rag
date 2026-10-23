"""Summary requests keep one bounded call and use low effort on the Luna alias."""

import json
from types import SimpleNamespace
from typing import Any

import pytest
from openai import omit
from smart_rag_agents.prompts.registry import load_prompt
from smart_rag_core.gateways import summary_model
from smart_rag_core.memory.versions import SUMMARY_PROMPT_VERSION


@pytest.mark.parametrize("model_id", ["gpt-6-luna", "gpt-4o-mini"])
def test_summary_provider_request_is_bounded_and_role_specific(
    monkeypatch: pytest.MonkeyPatch,
    model_id: str,
) -> None:
    """Luna summary effort must not add unsupported arguments to older models."""
    captured: dict[str, Any] = {}

    def create(**kwargs: Any) -> SimpleNamespace:
        """Capture one bounded provider request and return a compact summary."""
        captured.update(kwargs)
        return SimpleNamespace(
            id="summary-test",
            status="completed",
            output_text=json.dumps(
                {"summary": "User discussed storage.", "preference_updates": []}
            ),
            usage=SimpleNamespace(input_tokens=40, output_tokens=15),
        )

    def client(**kwargs: Any) -> SimpleNamespace:
        """Record retry and timeout settings without constructing a provider client."""
        captured["client"] = kwargs
        return SimpleNamespace(responses=SimpleNamespace(create=create))

    monkeypatch.setattr(summary_model, "traced_openai_client", client)
    monkeypatch.setattr(
        summary_model, "ALLOWED_SUMMARY_MODEL_IDS", frozenset({model_id})
    )
    prompt = load_prompt(SUMMARY_PROMPT_VERSION)
    request = summary_model.SummaryModelRequest(
        messages="user: Explain storage.",
        prompt_text=prompt.path.read_text(encoding="utf8"),
        prompt_sha256=prompt.sha256,
        model_id=model_id,
        remaining_deadline_seconds=6,
    )
    response = summary_model.execute_summary("synthetic-test-key", request)
    assert response.summary == "User discussed storage."
    assert captured["model"] == model_id
    assert captured["max_output_tokens"] == 900
    assert captured["store"] is False
    assert captured["client"]["max_retries"] == 0
    assert captured["client"]["timeout"] == 6
    assert (
        captured["reasoning"] == {"effort": "low"}
        if model_id == "gpt-6-luna"
        else captured["reasoning"] is omit
    )
