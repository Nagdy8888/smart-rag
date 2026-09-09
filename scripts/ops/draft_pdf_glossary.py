"""Draft private glossary candidates from deterministic source evidence only."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import TypedDict

from smart_rag_core.ingestion.parser.adapters import parse_file
from smart_rag_core.ingestion.parser.types import ElementKind
from smart_rag_core.text.arabic_normalize import normalize_arabic_v1

_ACRONYM = re.compile(
    r"\b([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){0,4})\s+\(([A-Z]{2,12})\)"
)
_CODE = re.compile(r"\b([A-Z]{2,8}-[A-Z0-9]{2,16})\b")
_HEADING_TERM = re.compile(r"^[A-Z][A-Za-z0-9][A-Za-z0-9 /-]{2,80}$")
_ENTRY_KEY = re.compile(r"[^A-Za-z0-9._:-]+")


class _Candidate(TypedDict):
    """Internal candidate with terms. Never printed by the CLI."""

    kind: str
    locator: str
    canonical_term: str
    alias: str | None
    normalized_hash: str


def _row_hash(canonical: str, locator: str) -> str:
    """Hash one draft row without storing raw secrets.

    Args:
        canonical: Canonical term.
        locator: Page/heading locator.

    Returns:
        SHA-256 hex digest.
    """

    payload = f"{normalize_arabic_v1(canonical)}|{locator}".encode()
    return hashlib.sha256(payload).hexdigest()


def _entry_key(prefix: str, value: str) -> str:
    """Build an allow-listed glossary entry key.

    Args:
        prefix: Kind prefix such as ``acr`` or ``id``.
        value: Source token.

    Returns:
        Key matching ``[A-Za-z0-9._:-]+``.
    """

    cleaned = _ENTRY_KEY.sub("-", value).strip("-._:")
    if not cleaned:
        cleaned = "term"
    return f"{prefix}-{cleaned}"[:64]


def collect_glossary_candidates(path: Path) -> tuple[_Candidate, ...]:
    """Collect locator-backed glossary candidates, including private terms.

    Args:
        path: Local document. Callers must not print term values.

    Returns:
        Candidates with hashes, locators, and private terms.
    """

    payload = path.read_bytes()
    file_digest = hashlib.sha256(payload).hexdigest()
    parsed = parse_file(path, file_digest)
    rows: list[_Candidate] = []
    seen: set[str] = set()
    for element in parsed.elements:
        locator = str(element.locator)
        text = (element.text or "").strip()
        if not text:
            continue
        if element.kind is ElementKind.HEADING and _HEADING_TERM.match(text):
            digest = _row_hash(text, locator)
            if digest not in seen:
                seen.add(digest)
                rows.append(
                    {
                        "kind": "heading",
                        "normalized_hash": digest,
                        "locator": locator,
                        "canonical_term": text,
                        "alias": None,
                    }
                )
        for match in _ACRONYM.finditer(text):
            expansion = match.group(1).strip()
            acronym = match.group(2).strip()
            digest = _row_hash(acronym, locator)
            if digest in seen:
                continue
            seen.add(digest)
            rows.append(
                {
                    "kind": "acronym",
                    "normalized_hash": digest,
                    "locator": locator,
                    "canonical_term": expansion,
                    "alias": acronym,
                }
            )
        for match in _CODE.finditer(text):
            code = match.group(1)
            digest = _row_hash(code, locator)
            if digest in seen:
                continue
            seen.add(digest)
            rows.append(
                {
                    "kind": "identifier",
                    "normalized_hash": digest,
                    "locator": locator,
                    "canonical_term": code,
                    "alias": None,
                }
            )
    return tuple(rows)


def draft_glossary_rows(path: Path) -> tuple[dict[str, object], ...]:
    """Propose glossary candidates from headings, acronyms, and identifiers.

    Args:
        path: Local document. Source text is not printed.

    Returns:
        Rows with hashes and locators only in the returned objects. Callers
        must write under ``.private-eval/`` and never auto-approve.
    """

    return tuple(
        {
            "kind": item["kind"],
            "normalized_hash": item["normalized_hash"],
            "locator": item["locator"],
        }
        for item in collect_glossary_candidates(path)
    )


def build_glossary_import_entries(
    candidates: tuple[_Candidate, ...],
) -> tuple[dict[str, object], ...]:
    """Build owner/admin import entries, skipping ambiguous aliases.

    Args:
        candidates: Internal candidates with private terms.

    Returns:
        Import entries with ``company`` scope. Ambiguous acronyms and
        alias-equals-canonical rows are omitted rather than auto-fixed.
    """

    alias_to_canonical: dict[str, str] = {}
    ambiguous: set[str] = set()
    for item in candidates:
        alias = item["alias"]
        if alias is None:
            continue
        alias_norm = normalize_arabic_v1(alias)
        canonical_norm = normalize_arabic_v1(item["canonical_term"])
        if alias_norm == "" or canonical_norm == "" or alias_norm == canonical_norm:
            continue
        prior = alias_to_canonical.get(alias_norm)
        if prior is None:
            alias_to_canonical[alias_norm] = canonical_norm
        elif prior != canonical_norm:
            ambiguous.add(alias_norm)
    entries: list[dict[str, object]] = []
    used_keys: set[str] = set()
    used_canonical: set[str] = set()
    skipped_ambiguous = 0
    for item in candidates:
        canonical = item["canonical_term"].strip()
        canonical_norm = normalize_arabic_v1(canonical)
        if canonical_norm == "" or canonical_norm in used_canonical:
            continue
        alias = item["alias"]
        aliases: list[dict[str, str]] = []
        if alias is not None:
            alias_norm = normalize_arabic_v1(alias)
            if alias_norm in ambiguous:
                skipped_ambiguous += 1
                continue
            if alias_norm == canonical_norm:
                continue
            aliases.append({"alias": alias, "language": "en"})
        if item["kind"] == "identifier" and not aliases:
            continue
        if item["kind"] == "heading" and not aliases:
            continue
        prefix = "acr" if item["kind"] == "acronym" else "id"
        key_source = alias or canonical
        key = _entry_key(prefix, key_source)
        ordinal = 1
        original = key
        while key in used_keys:
            ordinal += 1
            key = f"{original[:60]}-{ordinal}"[:64]
        used_keys.add(key)
        used_canonical.add(canonical_norm)
        entry_type = "acronym" if item["kind"] == "acronym" else "product_code"
        entries.append(
            {
                "entry_key": key,
                "canonical_term": canonical[:256],
                "language": "en",
                "entry_type": entry_type,
                "effective_scope": "company",
                "aliases": aliases,
                "source_hash": item["normalized_hash"],
                "locator": item["locator"],
            }
        )
    return tuple(entries)


def main(argv: list[str] | None = None) -> int:
    """Write a private draft and print counts/hashes only.

    Args:
        argv: Optional CLI arguments.

    Returns:
        Process exit code.
    """

    parser = argparse.ArgumentParser(
        description="Draft private glossary candidates. Never auto-approves."
    )
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(".private-eval/glossary-draft.json"),
    )
    parser.add_argument(
        "--import-payload",
        type=Path,
        default=Path(".private-eval/glossary-import.json"),
        help="Gitignored payload with terms for owner/admin import.",
    )
    args = parser.parse_args(argv)
    if not args.path.is_file():
        print("glossary_draft_missing_file")
        return 2
    candidates = collect_glossary_candidates(args.path)
    rows = tuple(
        {
            "kind": item["kind"],
            "normalized_hash": item["normalized_hash"],
            "locator": item["locator"],
        }
        for item in candidates
    )
    entries = build_glossary_import_entries(candidates)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"rows": list(rows)}, indent=2), encoding="utf-8")
    args.import_payload.parent.mkdir(parents=True, exist_ok=True)
    args.import_payload.write_text(
        json.dumps(
            {
                "source_name": "private-pdf-glossary",
                "source_version": "v1",
                "auto_approved": False,
                "entries": list(entries),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"row_count={len(rows)}")
    print(f"import_entry_count={len(entries)}")
    print(f"draft_path_set={str(args.out.exists()).lower()}")
    print(f"import_payload_set={str(args.import_payload.exists()).lower()}")
    print("auto_approved=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
