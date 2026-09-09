"""Holdout-blind loaders for the private PDF evaluation dataset."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from smart_rag_core.evaluation.holdout import (
    HoldoutAccess,
    HoldoutSealedError,
    assert_holdout_allowed,
)
from smart_rag_core.evaluation.private_pdf.schema import (
    PrivatePdfCase,
    PrivatePdfLabeledCase,
)
from smart_rag_core.evaluation.private_pdf.seal import assert_holdout_path_hidden


def _as_mapping(item: object) -> dict[str, object]:
    """Coerce a JSON object to a string-keyed mapping.

    Args:
        item: Parsed JSON value.

    Returns:
        String-keyed mapping.

    Raises:
        ValueError: When the value is not an object.
    """

    if not isinstance(item, dict):
        raise ValueError("invalid_private_pdf_case")
    typed = cast(dict[Any, object], item)
    mapping: dict[str, object] = {}
    for key, value in typed.items():
        mapping[str(key)] = value
    return mapping


def _as_sequence(value: object) -> tuple[object, ...]:
    """Return a tuple for JSON arrays.

    Args:
        value: JSON array or other value.

    Returns:
        Tuple of items, or empty when not a list/tuple.
    """

    if isinstance(value, list):
        return tuple(cast(list[object], value))
    if isinstance(value, tuple):
        return tuple(cast(tuple[object, ...], value))
    return ()


def _case_from_mapping(item: object) -> PrivatePdfCase:
    """Parse one JSON object into a Git-safe private-PDF case.

    Args:
        item: JSON mapping.

    Returns:
        Case without question/answer/excerpt fields.

    Raises:
        ValueError: Missing required keys.
    """

    mapping = _as_mapping(item)
    chunk_raw = _as_sequence(mapping.get("chunk_ids", ()))
    pages_raw = _as_sequence(mapping.get("page_numbers", ()))
    headings_raw = _as_sequence(mapping.get("heading_paths", ()))
    terms_raw = _as_sequence(mapping.get("required_terms", ()))
    actor = mapping.get("acl_actor_id")
    reviewer = mapping.get("reviewer")
    query_class = mapping.get("query_class", "factual_definition")
    profile_id = mapping.get("expected_profile_id", "hybrid_default_v1")
    scope = mapping.get("expected_scope", "unscoped")
    return PrivatePdfCase(
        case_id=str(mapping["case_id"]),
        split=str(mapping["split"]),
        source_family_id=str(mapping["source_family_id"]),
        query_class=str(query_class),
        chunk_ids=tuple(UUID(str(value)) for value in chunk_raw),
        page_numbers=tuple(int(str(value)) for value in pages_raw),
        heading_paths=tuple(str(value) for value in headings_raw),
        required_terms=tuple(str(value) for value in terms_raw),
        expected_profile_id=str(profile_id),
        expected_scope=str(scope),
        expected_refusal=bool(mapping.get("expected_refusal", False)),
        acl_actor_id=str(actor) if actor is not None else None,
        human_approved=bool(mapping.get("human_approved", False)),
        generated_only=bool(mapping.get("generated_only", True)),
        reviewer=str(reviewer) if reviewer else None,
    )


def _cases_from_json(raw: object) -> tuple[PrivatePdfCase, ...]:
    """Parse a dataset payload into cases.

    Args:
        raw: JSON object or list.

    Returns:
        Parsed cases.

    Raises:
        ValueError: Malformed dataset.
    """

    if isinstance(raw, dict):
        mapping = _as_mapping(cast(dict[Any, object], raw))
        items = mapping.get("cases", ())
    else:
        items = raw
    if not isinstance(items, list):
        raise ValueError("invalid_private_pdf_dataset")
    parsed: list[PrivatePdfCase] = []
    for item in cast(list[object], items):
        parsed.append(_case_from_mapping(item))
    return tuple(parsed)


def read_private_pdf_payload(path: Path) -> tuple[PrivatePdfCase, ...]:
    """Load cases from a private JSON file without returning source text.

    Args:
        path: Draft or sealed JSON. Holdout custody paths are rejected.

    Returns:
        Parsed cases.

    Raises:
        HoldoutSealedError: Path looks like holdout custody.
        ValueError: Malformed JSON.
    """

    assert_holdout_path_hidden(path)
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    return _cases_from_json(raw)


def load_private_pdf_tuning_cases(path: Path) -> tuple[PrivatePdfCase, ...]:
    """Load development rows only. Holdout labels stay unreachable.

    Args:
        path: Gitignored draft/sealed file that is not holdout custody.

    Returns:
        Development-split cases.

    Raises:
        HoldoutSealedError: Path is holdout custody.
    """

    cases = read_private_pdf_payload(path)
    return tuple(case for case in cases if case.split == "development")


def load_private_pdf_open_splits(path: Path) -> tuple[PrivatePdfCase, ...]:
    """Load development and qualification. Holdout stays sealed.

    Args:
        path: Gitignored dataset file that is not holdout custody.

    Returns:
        Open-split cases.

    Raises:
        HoldoutSealedError: Path is holdout custody.
    """

    cases = read_private_pdf_payload(path)
    return tuple(case for case in cases if case.split != "holdout")


def load_private_pdf_holdout(
    path: Path,
    *,
    holdout_access: HoldoutAccess,
) -> tuple[PrivatePdfCase, ...]:
    """Load holdout rows only with an authorized one-time token.

    Args:
        path: Reviewer-controlled holdout file.
        holdout_access: Allow-listed purpose and actor.

    Returns:
        Holdout cases.

    Raises:
        HoldoutSealedError: Default deny or missing actor/purpose.
    """

    assert_holdout_allowed(holdout_access)
    if ".private-eval" in {part.lower() for part in path.parts} and (
        "holdout" not in {part.lower() for part in path.parts}
    ):
        raise HoldoutSealedError("private pdf holdout is sealed")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    cases = _cases_from_json(raw)
    return tuple(case for case in cases if case.split == "holdout")


def _labeled_from_mapping(item: object) -> PrivatePdfLabeledCase:
    """Parse one JSON object including private question fields.

    Args:
        item: JSON mapping.

    Returns:
        Labeled case.

    Raises:
        ValueError: Missing question or malformed mapping.
    """

    mapping = _as_mapping(item)
    question = str(mapping.get("question", "")).strip()
    if not question:
        raise ValueError("missing_private_pdf_question")
    facts_raw = mapping.get("atomic_facts", ())
    facts: tuple[str, ...]
    if isinstance(facts_raw, list):
        facts = tuple(str(value) for value in cast(list[object], facts_raw))
    elif isinstance(facts_raw, tuple):
        facts = tuple(str(value) for value in cast(tuple[object, ...], facts_raw))
    else:
        facts = ()
    return PrivatePdfLabeledCase(
        meta=_case_from_mapping(item),
        question=question,
        expected_answer=str(mapping.get("expected_answer", "")),
        atomic_facts=facts,
    )


def read_private_pdf_labeled(path: Path) -> tuple[PrivatePdfLabeledCase, ...]:
    """Load labeled rows from a gitignored file. Holdout custody is rejected.

    Args:
        path: Draft or sealed JSON that is not holdout custody.

    Returns:
        Labeled cases including questions.

    Raises:
        HoldoutSealedError: Path looks like holdout custody.
        ValueError: Malformed JSON or missing questions.
    """

    assert_holdout_path_hidden(path)
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        mapping = _as_mapping(cast(dict[Any, object], raw))
        items = mapping.get("cases", ())
    else:
        items = raw
    if not isinstance(items, list):
        raise ValueError("invalid_private_pdf_dataset")
    parsed: list[PrivatePdfLabeledCase] = []
    for item in cast(list[object], items):
        parsed.append(_labeled_from_mapping(item))
    return tuple(parsed)


def load_private_pdf_labeled_open_splits(
    path: Path,
) -> tuple[PrivatePdfLabeledCase, ...]:
    """Load development and qualification labeled rows. Holdout stays sealed.

    Args:
        path: Gitignored dataset file that is not holdout custody.

    Returns:
        Open-split labeled cases.

    Raises:
        HoldoutSealedError: Path is holdout custody.
    """

    return tuple(
        case for case in read_private_pdf_labeled(path) if case.meta.split != "holdout"
    )


def load_private_pdf_labeled_tuning(
    path: Path,
) -> tuple[PrivatePdfLabeledCase, ...]:
    """Load development labeled rows only.

    Args:
        path: Gitignored dataset file that is not holdout custody.

    Returns:
        Development labeled cases.

    Raises:
        HoldoutSealedError: Path is holdout custody.
    """

    return tuple(
        case
        for case in read_private_pdf_labeled(path)
        if case.meta.split == "development"
    )


def load_private_pdf_labeled_qualification(
    path: Path,
) -> tuple[PrivatePdfLabeledCase, ...]:
    """Load qualification labeled rows only. Holdout stays sealed.

    Args:
        path: Gitignored dataset file that is not holdout custody.

    Returns:
        Qualification labeled cases.

    Raises:
        HoldoutSealedError: Path is holdout custody.
    """

    return tuple(
        case
        for case in read_private_pdf_labeled(path)
        if case.meta.split == "qualification"
    )


def load_private_pdf_labeled_holdout(
    path: Path,
    *,
    holdout_access: HoldoutAccess,
) -> tuple[PrivatePdfLabeledCase, ...]:
    """Load holdout labeled rows with an authorized one-time token.

    Args:
        path: Reviewer-controlled holdout file outside the repository.
        holdout_access: Allow-listed purpose and actor.

    Returns:
        Holdout labeled cases.

    Raises:
        HoldoutSealedError: Default deny, missing actor/purpose, or a
            workspace-relative private-eval path that is not custody.
        ValueError: Malformed JSON or missing questions.
    """

    assert_holdout_allowed(holdout_access)
    parts = {part.lower() for part in path.parts}
    if ".private-eval" in parts and "holdout" not in parts:
        raise HoldoutSealedError("private pdf holdout is sealed")
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        mapping = _as_mapping(cast(dict[Any, object], raw))
        items = mapping.get("cases", ())
    else:
        items = raw
    if not isinstance(items, list):
        raise ValueError("invalid_private_pdf_dataset")
    parsed: list[PrivatePdfLabeledCase] = []
    for item in cast(list[object], items):
        labeled = _labeled_from_mapping(item)
        if labeled.meta.split == "holdout":
            parsed.append(labeled)
    return tuple(parsed)


def development_labels_are_sealed(cases: tuple[PrivatePdfCase, ...]) -> bool:
    """Return whether every development row is named-human approved.

    Args:
        cases: Development-split cases.

    Returns:
        True when the split is non-empty and none of the rows are generated-only.
    """

    if not cases:
        return False
    return all(
        (not case.generated_only) and case.human_approved and bool(case.reviewer)
        for case in cases
    )


def open_splits_are_sealed(cases: tuple[PrivatePdfCase, ...]) -> bool:
    """Return whether development and qualification rows are named-human approved.

    Args:
        cases: Open-split cases (holdout already dropped).

    Returns:
        True when both open splits are non-empty and named-human sealed.
    """

    development = tuple(case for case in cases if case.split == "development")
    qualification = tuple(case for case in cases if case.split == "qualification")
    if not development or not qualification:
        return False
    return development_labels_are_sealed(development) and all(
        (not case.generated_only) and case.human_approved and bool(case.reviewer)
        for case in qualification
    )
