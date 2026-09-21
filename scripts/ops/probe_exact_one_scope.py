"""Count-only exact-one scope probe for one canonical version.

Reads questions from a gitignored gold file. Prints resolution, profile
id, version match, and whether selector text remains in the ranking
query. Never prints titles or question text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import UUID

import psycopg

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from smart_rag_core.retrieval.source_scope import (  # noqa: E402
    resolve_retrieval_scope,
    strip_source_selectors,
)
from smart_rag_core.security.identity import CallerContext, UserRole  # noqa: E402


def _parse_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines from one gitignored env file.

    Args:
        path: Env file path.

    Returns:
        Mapping of keys to values.
    """

    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _questions(path: Path) -> list[str]:
    """Load question strings from a private gold JSON file.

    Args:
        path: Gitignored gold file.

    Returns:
        Question texts. Empty when the file is missing or malformed.
    """

    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get("questions") or payload.get("items") or []
    else:
        return []
    questions: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = row.get("question") or row.get("text")
        if isinstance(text, str) and text.strip():
            questions.append(text.strip())
    return questions


def main(argv: list[str] | None = None) -> int:
    """Print exact-one counts for private questions against one version.

    Args:
        argv: Optional CLI arguments.

    Returns:
        ``0`` when every question is exact-one on the expected version.
        ``2`` on configuration failure. ``3`` when a question is not
        exact-one.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument("--gold-file", type=Path, required=True)
    parser.add_argument("--version-id", type=UUID, required=True)
    args = parser.parse_args(argv)
    resolved = args.gold_file.resolve()
    if ".private-eval" not in {part.casefold() for part in resolved.parts}:
        print("blocked=gold_file_not_private")
        return 2
    questions = _questions(resolved)
    if not questions:
        print("blocked=no_questions")
        return 2
    env = _parse_env(REPO / ".env")
    env.update(_parse_env(REPO / ".env.compose"))
    url = env.get("OPERATOR_SUPABASE_DB_URL", "").strip()
    if not url:
        print("missing_operator_url")
        return 2
    exact_one = 0
    version_matches = 0
    selector_absent = 0
    profiles: dict[str, int] = {}
    with psycopg.connect(url) as connection:
        connection.execute("SET ROLE postgres")
        owner = connection.execute(
            """
            SELECT user_id::text, app.current_authorization_version()
            FROM app.profiles
            WHERE role = 'owner'::app.user_role
              AND disabled_at IS NULL
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if owner is None:
            print("blocked=no_owner")
            return 2
        caller = CallerContext(
            user_id=str(owner[0]),
            role=UserRole.OWNER,
            authorization_version=int(owner[1]),
        )
        connection.execute("SET ROLE app_api")
        for question in questions:
            scope = resolve_retrieval_scope(
                caller=caller,
                requested_sources=(),
                whole_document=False,
                connection=connection,
                query_text=question,
            )
            profiles[scope.candidate_profile_id] = (
                profiles.get(scope.candidate_profile_id, 0) + 1
            )
            if scope.resolution.value == "exact_one":
                exact_one += 1
            if scope.version_id == args.version_id:
                version_matches += 1
            ranking = strip_source_selectors(question, scope.selector_texts)
            if all(selector not in ranking for selector in scope.selector_texts):
                selector_absent += 1
    print(f"questions={len(questions)}")
    print(f"exact_one={exact_one}")
    print(f"version_matches={version_matches}")
    print(f"selector_absent_from_ranking={selector_absent}")
    print(f"profiles={json.dumps(profiles, sort_keys=True)}")
    if (
        exact_one != len(questions)
        or version_matches != len(questions)
        or selector_absent != len(questions)
    ):
        print("blocked=scope_not_exact_one")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
