"""Connected evaluation must contain real questions and flag wrong-topic cited answers."""

import json
from pathlib import Path

from scripts.eval_conversation_memory import assess


def test_connected_fixture_has_fifty_valid_questions_including_real_arabic() -> None:
    """Encoding damage cannot masquerade as a multilingual agent regression."""
    path = (
        Path(__file__).resolve().parents[1] / "fixtures/query-memory-linked50-v4.json"
    )
    turns = json.loads(path.read_text(encoding="utf8"))["turns"]
    assert len(turns) == len({turn["id"] for turn in turns}) == 50
    assert all("???" not in turn["question"] for turn in turns)
    for turn in turns:
        if turn["id"] in {"m35", "m36", "m37"}:
            assert sum("\u0600" <= char <= "\u06ff" for char in turn["question"]) >= 20


def test_a_cited_different_diagram_is_still_a_failed_followup() -> None:
    """An available image and a citation are insufficient when the remembered referent is wrong."""
    turn = {
        "scope": "company_documents",
        "check": "figure",
        "required_patterns": [r"Figure\s+2[-\u2013]1"],
    }
    issues = assess(
        turn,
        "Figure 8-1 explains another framework. [[figure:sample]]",
        [{"source_unavailable": False}],
    )
    assert any(issue.startswith("required_topic_missing:") for issue in issues)


def test_arabic_preamble_cannot_disguise_an_untranslated_table() -> None:
    """The requested table language applies to its cells, not just the introduction."""
    answer = (
        "\u0645\u0642\u0627\u0631\u0646\u0629 " * 20
        + "\n| Approach | Benefit |\n| --- | --- |\n| Storage | Durable |"
    )
    issues = assess(
        {"scope": "company_documents", "check": "arabic_table"},
        answer,
        [{"source_unavailable": False}],
    )
    assert "arabic_table_cells_missing" in issues


def test_mentioning_old_count_does_not_pass_current_count_recall() -> None:
    """An invented correction must fail even when the expected numeral is present."""
    issues = assess(
        {"scope": "general_knowledge", "check": "final_recall"},
        "Harbor Maple: one additional reviewer (revised from nine). "
        "Concise English unless Arabic is requested.",
        [],
    )
    assert "current_reviewer_limit_contradicted" in issues
