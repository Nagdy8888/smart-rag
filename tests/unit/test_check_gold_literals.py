"""Unit tests for the gold-literal guard in ``scripts/check_gold_literals.py``."""

from __future__ import annotations

from pathlib import Path

from scripts.check_gold_literals import load_allowlist, normalize_source, scan


def test_regex_escapes_are_stripped() -> None:
    """A whitespace regex still matches the plain phrase."""

    assert "alpha beta gamma" in normalize_source(
        r'X = re.compile(r"(?i)alpha\s+beta\s+gamma")'
    )


def test_rare_phrases_fail_and_common_phrases_are_ignored() -> None:
    """Two rare hits fail a file; a phrase in three files is vocabulary."""

    phrases = {
        "alpha beta gamma": ("set-a", "q1"),
        "delta epsilon zeta": ("set-a", "q2"),
        "common words here": ("set-b", "q3"),
    }
    app = {
        "pkg/one.py": 'A = r"alpha\\s+beta\\s+gamma"\nB = "delta epsilon zeta"\nC = "common words here"\n',
        "pkg/two.py": '"common words here"\n',
        "pkg/three.py": '"common words here"\n',
    }
    failing, warnings = scan(app, {}, phrases, frozenset())
    assert list(failing) == ["pkg/one.py"]
    assert {hit.question_id for hit in failing["pkg/one.py"]} == {"q1", "q2"}
    assert warnings == {}


def test_single_hit_and_allowlist_do_not_fail() -> None:
    """One rare hit, or an allowlisted path, never fails."""

    phrases = {"alpha beta gamma": ("s", "q1"), "delta epsilon zeta": ("s", "q2")}
    app = {
        "pkg/one.py": '"alpha beta gamma"\n',
        "pkg/old.md": "alpha beta gamma and delta epsilon zeta\n",
    }
    failing, _ = scan(app, {}, phrases, frozenset({"pkg/old.md"}))
    assert failing == {}


def test_warn_roots_never_fail() -> None:
    """Test files are reported as warnings only."""

    phrases = {"alpha beta gamma": ("s", "q1"), "delta epsilon zeta": ("s", "q2")}
    failing, warnings = scan(
        {},
        {"tests/unit/t.py": "alpha beta gamma delta epsilon zeta"},
        phrases,
        frozenset(),
    )
    assert failing == {}
    assert len(warnings["tests/unit/t.py"]) == 2


def test_allowlist_parsing(tmp_path: Path) -> None:
    """Comments and blank lines are ignored."""

    path = tmp_path / "allow.txt"
    path.write_text("# header\n\npkg/a.md  # frozen\n", encoding="utf-8")
    assert load_allowlist(path) == frozenset({"pkg/a.md"})
