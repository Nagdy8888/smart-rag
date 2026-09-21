"""Unit test that sample-PDF gold stays out of production modules."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_PRODUCTION_ROOTS = (
    _REPO / "packages",
    _REPO / "apps",
)
_FORBIDDEN = (
    "978-1-098-17650-1",
    "Building Applications with AI Agents",
)


def test_production_modules_do_not_embed_sample_pdf_gold() -> None:
    """Production packages must not contain the sample book identifiers."""

    hits: list[str] = []
    for root in _PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in _FORBIDDEN):
                hits.append(str(path.relative_to(_REPO)))
    assert hits == []
