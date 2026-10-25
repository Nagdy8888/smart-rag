"""Synthetic offline Docker proof for isolated figure rendering."""

from __future__ import annotations

import hashlib
from unittest.mock import patch

from smart_rag_core.ingestion.figures.materialize import materialize_pdf_figures
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
)
from smart_rag_core.ingestion.parser.types import ParseDisposition
from smart_rag_core.settings.base import get_process_environ

from tests.unit import test_pdf_native_types as native_fixtures
from tests.unit.typed_attrs import typed_attr


def test_figure_rendering_stays_in_no_network_parser() -> None:
    """Worker consumes bounded rasters without reopening the source PDF."""
    import pytest

    image = get_process_environ("SECURITY_PARSER_TEST_IMAGE")
    if not image:
        pytest.skip("Set SECURITY_PARSER_TEST_IMAGE to a rebuilt parser image")
    payload: bytes = typed_attr(native_fixtures, "_pdf_bytes")()
    launcher = ParserSandboxLauncher(SandboxLaunchConfig(image=image))
    result = launcher.run(
        payload=payload,
        content_hash=hashlib.sha256(payload).hexdigest(),
        filename="synthetic.pdf",
        format_key="pdf",
    )
    assert result.disposition is not ParseDisposition.FAILED
    with patch("smart_rag_core.ingestion.figures.materialize.fitz.open") as native_open:
        updated, assets = materialize_pdf_figures(
            result, payload, lambda _png: "A square."
        )
        native_open.assert_not_called()
    assert assets
    assert all(asset.png.startswith(b"\x89PNG") for asset in assets)
    assert all("sandbox_png" not in element.metadata for element in updated.elements)
