"""The image probe names every latency packet in order."""

from __future__ import annotations

import pytest

from scripts import probe_latency_image
from scripts.probe_latency_image import CHECKS, probe_lines


def test_probe_lines_cover_every_packet_in_order() -> None:
    """Eight packet lines come first, then the two info lines."""

    lines = probe_lines()
    assert len(CHECKS) == 8
    assert len(lines) == 10
    for index, line in enumerate(lines[:8]):
        packet, state = line.split(" ")
        assert packet == f"L{index}"
        assert state in {"present", "MISSING"}
    assert lines[0] == "L0 present"
    assert lines[8].startswith("rerank_prompt_version=")
    assert lines[9].startswith("event_store_pool_max=")


def test_probe_expected_value_mismatch_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A wrong expected value or a missing module reports MISSING."""

    monkeypatch.setattr(
        probe_latency_image,
        "CHECKS",
        (
            (
                "LX",
                "smart_rag_core.retrieval.rerank_versions",
                "RERANK_PROMPT_VERSION",
                "not-a-version",
            ),
            ("LY", "smart_rag_no_such_package.module", "NAME", None),
        ),
    )
    lines = probe_latency_image.probe_lines()
    assert lines[:2] == ["LX MISSING", "LY MISSING"]
