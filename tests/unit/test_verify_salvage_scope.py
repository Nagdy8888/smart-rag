"""The verify node runs structural and general claim-fill salvages only."""

from __future__ import annotations

import inspect
import re

import smart_rag_core.query_answer.generate_grounded as grounded
from smart_rag_agents.query.nodes import verify


def test_verify_salvage_loop_names_are_general() -> None:
    """Verify runs structural and general claim-fill salvages only."""

    source = inspect.getsource(verify)
    names = set(re.findall(r"\bsalvage_[a-z_]+\b", source)) - {"salvage_fn"}
    assert names == {
        "salvage_named_code_definition",
        "salvage_named_table_block",
        "salvage_anchor_claim_fill",
    }


def test_question_specific_salvages_are_gone() -> None:
    """Deleted salvage helpers are not importable."""

    for name in (
        "salvage_refused_literal_claims",
        "salvage_query_literal_extractive",
        "salvage_expose_mode_labels",
        "salvage_listed_literals",
        "salvage_method_or_heading_label",
    ):
        assert not hasattr(grounded, name)
