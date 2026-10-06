r"""Fail when private gold phrases are baked into application source or prompts.

General-fix guard for the answer-quality repair loop. It loads every private
gold file ``.private-eval/*v1.json`` (gitignored), normalizes each canonical
phrase and alias of at least ``MIN_PHRASE_CHARS`` characters, and searches
tracked application files. Regex escapes are stripped from source first so a
pattern such as ``alpha\\s+beta`` still matches the phrase ``alpha beta``.

A phrase that occurs in more than ``RARE_FILE_LIMIT`` application files is
ordinary vocabulary and is ignored. An application file fails when it holds
at least ``FAIL_HITS_PER_FILE`` rare phrases and is not in the allowlist.
Files under ``WARN_ROOTS`` (tests, scripts) are reported but never fail.

Output is paths, line numbers, set names, question ids, and counts. Phrases
are never printed. Without private gold files (for example in CI) the check
prints ``skipped`` and exits 0.

Example:
    ``uv run python scripts/check_gold_literals.py``
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.evaluation.dual_metric import normalize_answer_text  # noqa: E402

APP_ROOTS: tuple[str, ...] = ("packages", "apps/agents", "apps/backend")
WARN_ROOTS: tuple[str, ...] = ("tests", "scripts")
SUFFIXES: tuple[str, ...] = (".py", ".md")
MIN_PHRASE_CHARS = 8
RARE_FILE_LIMIT = 2
FAIL_HITS_PER_FILE = 2
WINDOW_LINES = 3
ALLOWLIST = REPO / "scripts" / "gold_literal_allowlist.txt"
PRIVATE_DIR = REPO / ".private-eval"
_REGEX_ESCAPE = re.compile(r"\\[sSbBnwWd][+*?]?")


@dataclass(frozen=True, slots=True)
class Hit:
    """One rare gold phrase found in one file.

    Attributes:
        path: Repository-relative POSIX path.
        line: 1-based line where the phrase starts (window search).
        set_name: Gold file stem.
        question_id: Gold question id.
    """

    path: str
    line: int
    set_name: str
    question_id: str


def normalize_source(text: str) -> str:
    """Strip regex escapes and normalize like the scorer, collapsing spaces.

    Args:
        text: Source text.

    Returns:
        Normalized text.
    """

    stripped = text.replace("(?i)", " ")
    stripped = _REGEX_ESCAPE.sub(" ", stripped).replace("\\", "")
    return " ".join(normalize_answer_text(stripped).split())


def load_gold_phrases(private_dir: Path) -> dict[str, tuple[str, str]]:
    """Load normalized gold phrases from every private ``*v1.json`` file.

    Args:
        private_dir: The ``.private-eval`` folder.

    Returns:
        Normalized phrase to ``(set_name, question_id)`` (first seen wins).
    """

    phrases: dict[str, tuple[str, str]] = {}
    for path in sorted(private_dir.glob("*v1.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = data if isinstance(data, list) else []
        for row in rows:
            if not isinstance(row, dict):
                continue
            for fact in row.get("facts") or []:
                if not isinstance(fact, dict):
                    continue
                for raw in [
                    *(fact.get("canonical") or []),
                    *(fact.get("aliases") or []),
                ]:
                    key = normalize_source(str(raw))
                    if len(key) >= MIN_PHRASE_CHARS:
                        phrases.setdefault(key, (path.stem, str(row.get("id") or "")))
    return phrases


def tracked_files(roots: Sequence[str], *, exclude_tests: bool) -> list[str]:
    """List tracked ``.py`` and ``.md`` files under roots.

    Args:
        roots: Repository-relative roots.
        exclude_tests: Drop paths with a ``tests`` directory segment
            (application roots); keep them for warning roots.

    Returns:
        POSIX paths.
    """

    output = subprocess.run(  # noqa: S603 - fixed local git ls-files argv
        ["git", "ls-files", *roots],  # noqa: S607
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [
        path
        for path in output.split()
        if path.endswith(SUFFIXES) and not (exclude_tests and "/tests/" in f"/{path}")
    ]


def first_line(raw_text: str, phrase: str) -> int:
    """Return the 1-based line where a phrase starts, by window search.

    Args:
        raw_text: Original file text.
        phrase: Normalized phrase.

    Returns:
        Line number, or 0 when only the whole-file text matches.
    """

    lines = raw_text.splitlines()
    for index in range(len(lines)):
        window = normalize_source(" ".join(lines[index : index + WINDOW_LINES]))
        if phrase in window:
            return index + 1
    return 0


def scan(
    app_texts: Mapping[str, str],
    warn_texts: Mapping[str, str],
    phrases: Mapping[str, tuple[str, str]],
    allowlist: frozenset[str],
) -> tuple[dict[str, list[Hit]], dict[str, list[Hit]]]:
    """Find rare gold phrases in application and warning files.

    Args:
        app_texts: Application path to raw text.
        warn_texts: Test/script path to raw text.
        phrases: Normalized phrase to ``(set_name, question_id)``.
        allowlist: Application paths exempt from failing.

    Returns:
        Failing application hits and warning hits, keyed by path.
    """

    app_norm = {path: normalize_source(text) for path, text in app_texts.items()}
    warn_norm = {path: normalize_source(text) for path, text in warn_texts.items()}
    app_hits: dict[str, list[Hit]] = defaultdict(list)
    warn_hits: dict[str, list[Hit]] = defaultdict(list)
    for phrase, (set_name, qid) in phrases.items():
        holders = [path for path, text in app_norm.items() if phrase in text]
        if len(holders) > RARE_FILE_LIMIT:
            continue
        for path in holders:
            if path in allowlist:
                continue
            app_hits[path].append(
                Hit(path, first_line(app_texts[path], phrase), set_name, qid)
            )
        for path, text in warn_norm.items():
            if phrase in text:
                warn_hits[path].append(
                    Hit(path, first_line(warn_texts[path], phrase), set_name, qid)
                )
    failing = {
        path: hits for path, hits in app_hits.items() if len(hits) >= FAIL_HITS_PER_FILE
    }
    return failing, dict(warn_hits)


def load_allowlist(path: Path) -> frozenset[str]:
    """Read allowlisted paths (one per line, ``#`` starts a comment).

    Args:
        path: Allowlist file.

    Returns:
        Repository-relative POSIX paths.
    """

    if not path.is_file():
        return frozenset()
    entries = (
        line.split("#", 1)[0].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
    )
    return frozenset(entry for entry in entries if entry)


def main(argv: list[str] | None = None) -> int:
    """Scan tracked files and report gold-phrase hits.

    Args:
        argv: Command-line arguments; ``None`` reads ``sys.argv``.

    Returns:
        0 when no application file fails (or ``--report-only``); 1 otherwise.
    """

    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args(argv)
    phrases = load_gold_phrases(PRIVATE_DIR)
    if not phrases:
        print("gold_literals skipped=no_private_gold")
        return 0
    read = lambda path: (REPO / path).read_text(encoding="utf-8", errors="replace")  # noqa: E731
    app_texts = {
        path: read(path) for path in tracked_files(APP_ROOTS, exclude_tests=True)
    }
    warn_texts = {
        path: read(path) for path in tracked_files(WARN_ROOTS, exclude_tests=False)
    }
    failing, warnings = scan(app_texts, warn_texts, phrases, load_allowlist(ALLOWLIST))
    for path, hits in sorted(failing.items()):
        print(f"FAIL {path} hits={len(hits)}")
        for hit in sorted(hits, key=lambda item: item.line):
            print(
                f"  hit {hit.path}:{hit.line} set={hit.set_name} id={hit.question_id}"
            )
    for path, hits in sorted(warnings.items()):
        print(f"WARN {path} hits={len(hits)}")
    print(
        f"gold_literals phrases={len(phrases)} app_files={len(app_texts)}"
        f" failing_files={len(failing)} warn_files={len(warnings)}"
    )
    if failing and not args.report_only:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
