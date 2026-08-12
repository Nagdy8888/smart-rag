"""Verify the current split-plan structure and locked file hashes.

Run without arguments to check structure, ownership guardrails, navigation,
and SHA-256 hashes. Run with ``--update`` only after an approved plan amendment
to rewrite the integrity lock from the validated current files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
PLAN_DIR = ROOT / ".cursor" / "plans" / "hybrid-graph-rag"
LOCK_PATH = PLAN_DIR / "plan-integrity-lock.json"
PHASE_SLUGS = (
    "foundation",
    "identity-data",
    "ingestion",
    "hybrid-rag",
    "graphrag",
    "agent-intelligence",
    "stitch-specification",
    "frontend-integration",
    "local-release-candidate",
    "managed-staging",
    "production",
)
SPLIT_PHASE_NUMBERS = tuple(range(6, 12))
BASE_CANONICAL_FILES = (
    ".cursor/plans/hybrid-graph-rag_ab5281ef.plan.md",
    ".cursor/plans/hybrid-graph-rag/00-global-contracts.md",
    *(
        f".cursor/plans/hybrid-graph-rag/{number:02d}-phase-{slug}.md"
        for number, slug in enumerate(PHASE_SLUGS, start=1)
    ),
    ".cursor/plans/hybrid-graph-rag/98-split-plan-completeness-audit.md",
    ".cursor/plans/hybrid-graph-rag/99-source-coverage.md",
    ".cursor/plans/hybrid-graph-rag/scripts/verify_plan_integrity.py",
    ".cursor/rules/00-plan-source-of-truth.mdc",
    ".cursor/skills/implement-api-security/SKILL.md",
    ".cursor/skills/implement-hybrid-retrieval/SKILL.md",
    ".cursor/skills/implement-ingestion-pipeline/SKILL.md",
    ".cursor/skills/implement-lightrag-graph/SKILL.md",
    ".cursor/skills/implement-observability-evals/SKILL.md",
    ".cursor/skills/implement-plan-phase/SKILL.md",
    ".cursor/skills/implement-query-agent/SKILL.md",
    ".cursor/skills/implement-rag-frontend/SKILL.md",
    ".cursor/skills/implement-structured-table/SKILL.md",
    ".cursor/skills/implement-supabase-security/SKILL.md",
    ".cursor/skills/scaffold-monorepo-layout/SKILL.md",
    ".cursor/skills/verify-release-gates/SKILL.md",
)
REQUIRED_PHASE_HEADINGS = (
    "## Mandatory model loading contract",
    "## Prerequisites",
    "## Relevant workspace skills",
    "## Scope lock",
    "## Ordered work packets",
    "## Phase sequence requirement",
    "## Stop conditions",
    "## Required exit record",
    "## Canonical detailed requirements",
    "## Phase deliver, review, and done gate",
)
REQUIRED_PACKET_HEADINGS = (
    "## Preconditions",
    "## Allowed outputs",
    "## Forbidden outputs",
    "## Ordered actions",
    "## Acceptance checks",
    "## Negative tests",
    "## Stop routes",
    "## Required evidence",
)
PACKET_LINK_PATTERN = re.compile(
    r"^(\d+)\. \[[ xX]\] \[([^\]]+)\]\(([^)]+)\)$",
    flags=re.MULTILINE,
)


def sha256_file(path: Path) -> str:
    """Calculate a file's SHA-256 digest.

    Args:
        path: Existing file to hash.

    Returns:
        Lowercase hexadecimal SHA-256 digest.

    Notes:
        Digests use LF-normalized bytes so Windows CRLF working trees match
        Linux CI checkouts of the same Git blob.
    """

    payload = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(payload).hexdigest()


def phase_path(number: int) -> Path:
    """Return the canonical path for a numbered phase.

    Args:
        number: One-based phase number from 1 through 11.

    Returns:
        Absolute path to the phase Markdown file.
    """

    return PLAN_DIR / f"{number:02d}-phase-{PHASE_SLUGS[number - 1]}.md"


def phase_source_dir(number: int) -> Path:
    """Return the split-source directory for a numbered phase.

    Args:
        number: One-based split phase number from 6 through 11.

    Returns:
        Absolute path to the phase's shared and packet contracts.
    """

    return PLAN_DIR / f"{number:02d}-phase-{PHASE_SLUGS[number - 1]}"


def repo_relative(path: Path) -> str:
    """Return a normalized repository-relative path.

    Args:
        path: Absolute path contained by the repository.

    Returns:
        POSIX-style path relative to the repository root.
    """

    return path.relative_to(ROOT).as_posix()


def canonical_files() -> tuple[str, ...]:
    """Discover every canonical wrapper, packet, and shared contract.

    Returns:
        Stable repository-relative paths included in the integrity lock.
    """

    discovered: set[str] = set(BASE_CANONICAL_FILES)
    shared_dir = PLAN_DIR / "shared"
    if shared_dir.is_dir():
        discovered.update(repo_relative(path) for path in shared_dir.rglob("*.md"))
    for number in SPLIT_PHASE_NUMBERS:
        source_dir = phase_source_dir(number)
        if source_dir.is_dir():
            discovered.update(repo_relative(path) for path in source_dir.rglob("*.md"))
    return tuple(sorted(discovered))


def phase_bundle_text(number: int) -> str:
    """Read a phase wrapper plus all of its split-source contracts.

    Args:
        number: One-based phase number.

    Returns:
        Concatenated canonical text used only by ownership validation.
    """

    paths = [phase_path(number)]
    source_dir = phase_source_dir(number)
    if source_dir.is_dir():
        paths.extend(sorted(source_dir.rglob("*.md")))
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


def require(condition: bool, message: str, errors: list[str]) -> None:
    """Append an integrity error when a condition is false.

    Args:
        condition: Expected invariant result.
        message: Error message recorded on failure.
        errors: Mutable error accumulator.
    """

    if not condition:
        errors.append(message)


def validate_phase_structure(errors: list[str]) -> None:
    """Validate uniform phase wrappers and completion gates.

    Args:
        errors: Mutable error accumulator.
    """

    for number in range(1, 12):
        path = phase_path(number)
        if not path.is_file():
            errors.append(f"Missing Phase {number}: {path.relative_to(ROOT)}")
            continue
        text = path.read_text(encoding="utf-8")
        require(
            f"phase: {number}" in text,
            f"Phase {number} frontmatter number is missing or wrong",
            errors,
        )
        for heading in REQUIRED_PHASE_HEADINGS:
            require(
                heading in text,
                f"Phase {number} is missing heading: {heading}",
                errors,
            )
        for label in ("- Deliver:", "- Review:", "- Done when:"):
            require(
                text.count(label) == 1,
                f"Phase {number} must contain exactly one {label}",
                errors,
            )
        require(
            "Do not set `status: complete` until every `Done when` item below is proven."
            in text,
            f"Phase {number} lacks the completion guard",
            errors,
        )
        if number in SPLIT_PHASE_NUMBERS:
            require(
                "split_source: true" in text,
                f"Phase {number} must declare split_source: true",
                errors,
            )
            canonical_body = text.split(
                "## Canonical detailed requirements", maxsplit=1
            )[-1].split("## Phase deliver, review, and done gate", maxsplit=1)[0]
            require(
                "redistributed" in canonical_body.lower(),
                f"Phase {number} does not declare redistributed packet contracts",
                errors,
            )
            require(
                re.search(r"^## (?:[8-9]|1[0-5])\.", canonical_body, re.MULTILINE)
                is None,
                f"Phase {number} wrapper still embeds a monolithic legacy section",
                errors,
            )


def validate_split_packets(errors: list[str]) -> None:
    """Validate linked packet contracts for split-source phases.

    Args:
        errors: Mutable error accumulator.
    """

    owned_requirement_ids: dict[str, str] = {}
    for number in SPLIT_PHASE_NUMBERS:
        wrapper = phase_path(number)
        if not wrapper.is_file():
            continue
        wrapper_text = wrapper.read_text(encoding="utf-8")
        source_dir = phase_source_dir(number)
        shared_contract = source_dir / "00-shared-contracts.md"
        packet_dir = source_dir / "packets"
        require(
            shared_contract.is_file(),
            f"Phase {number} lacks 00-shared-contracts.md",
            errors,
        )
        require(
            packet_dir.is_dir(),
            f"Phase {number} lacks a packets directory",
            errors,
        )
        ordered_section = wrapper_text.split("## Ordered work packets", maxsplit=1)[
            -1
        ].split("## Phase sequence requirement", maxsplit=1)[0]
        links = PACKET_LINK_PATTERN.findall(ordered_section)
        require(
            bool(links),
            f"Phase {number} has no linked ordered packet contracts",
            errors,
        )
        linked_paths: set[Path] = set()
        for expected, (number_text, title, destination) in enumerate(links, start=1):
            packet_number = int(number_text)
            require(
                packet_number == expected,
                f"Phase {number} packet order is not contiguous at {number_text}",
                errors,
            )
            clean_destination = destination.split("#", maxsplit=1)[0]
            packet_path = (wrapper.parent / clean_destination).resolve()
            linked_paths.add(packet_path)
            require(
                packet_path.is_file(),
                f"Phase {number} packet link is missing: {destination}",
                errors,
            )
            if not packet_path.is_file():
                continue
            packet_text = packet_path.read_text(encoding="utf-8")
            require(
                f"phase: {number}" in packet_text,
                f"{repo_relative(packet_path)} has the wrong phase",
                errors,
            )
            require(
                f"packet: {packet_number}" in packet_text,
                f"{repo_relative(packet_path)} has the wrong packet number",
                errors,
            )
            require(
                "status: pending" in packet_text,
                f"{repo_relative(packet_path)} must remain pending",
                errors,
            )
            require(
                f"# Packet {packet_number} — {title}" in packet_text,
                f"{repo_relative(packet_path)} title differs from its wrapper link",
                errors,
            )
            require(
                "../00-shared-contracts.md" in packet_text,
                f"{repo_relative(packet_path)} does not link its phase shared contract",
                errors,
            )
            for heading in REQUIRED_PACKET_HEADINGS:
                require(
                    packet_text.count(heading) == 1,
                    f"{repo_relative(packet_path)} must contain exactly one {heading}",
                    errors,
                )
            requirement_match = re.search(
                r"^requirement_ids:\s*\[([^\]]+)\]\s*$",
                packet_text,
                flags=re.MULTILINE,
            )
            require(
                requirement_match is not None,
                f"{repo_relative(packet_path)} lacks requirement_ids frontmatter",
                errors,
            )
            if requirement_match is not None:
                for requirement_id in requirement_match.group(1).split(","):
                    normalized = requirement_id.strip().strip("\"'")
                    previous = owned_requirement_ids.get(normalized)
                    require(
                        bool(normalized) and previous is None,
                        (
                            f"Duplicate or empty requirement ID {normalized!r} in "
                            f"{repo_relative(packet_path)}; first owner: {previous}"
                        ),
                        errors,
                    )
                    if normalized:
                        owned_requirement_ids[normalized] = repo_relative(packet_path)
        actual_paths = set(packet_dir.glob("*.md")) if packet_dir.is_dir() else set()
        require(
            linked_paths == actual_paths,
            f"Phase {number} wrapper links and packet files differ",
            errors,
        )


def validate_ownership(errors: list[str]) -> None:
    """Validate repaired cross-phase ownership boundaries.

    Args:
        errors: Mutable error accumulator.
    """

    phase_1 = phase_bundle_text(1)
    phase_2 = phase_bundle_text(2)
    phase_3 = phase_bundle_text(3)
    phase_4 = phase_bundle_text(4)
    phase_5 = phase_bundle_text(5)
    phase_6 = phase_bundle_text(6)
    phase_7 = phase_bundle_text(7)
    phase_8 = phase_bundle_text(8)
    phase_9 = phase_bundle_text(9)
    phase_10 = phase_bundle_text(10)
    phase_11 = phase_bundle_text(11)

    require(
        "Phase 1 CI ownership" in phase_1,
        "Phase 1 lacks local-versus-managed CI ownership",
        errors,
    )
    require(
        "Canonical migration ownership" in phase_2,
        "Phase 2 lacks canonical pgvector/Arabic migration ownership",
        errors,
    )
    require(
        "Through `LightRAGAdapter`" not in phase_3
        and "set the active workspace `updating`" not in phase_3,
        "Phase 3 still contains Phase 5 graph mutation instructions",
        errors,
    )
    phase_5_done = phase_5.split("- Done when:", maxsplit=1)[-1]
    require(
        "Combined meets gain" not in phase_5_done
        and "does not claim final Combined answer-quality success" in phase_5_done,
        "Phase 5 completion still claims Phase 6 Combined quality",
        errors,
    )
    require(
        "Phase 6 runtime Hybrid dependency contract" in phase_6,
        "Phase 6 lacks its local normative Hybrid runtime contract",
        errors,
    )
    require(
        "`rrf_k=60`" in phase_6
        and "Temporal behavior is" in phase_6
        and "UTC" in phase_6,
        "Phase 6 runtime contract lacks frozen RRF/temporal behavior",
        errors,
    )
    require(
        "must improve relationship/multi-hop success by at least 10 percentage points"
        in (PLAN_DIR / "00-global-contracts.md").read_text(encoding="utf-8")
        and "improves success by at least 10 percentage points" in phase_6,
        "Phase 6 does not own the global Combined improvement gate",
        errors,
    )
    require(
        "Phase 3 must already have created" in phase_4
        and "Phase 3" in phase_6
        and "OPENAI_DATA_GOVERNANCE.md" in phase_6
        and "SUBPROCESSOR_GOVERNANCE.md" in phase_6,
        "Later phases still ambiguously own OpenAI governance creation",
        errors,
    )
    require(
        "managed" in phase_9.lower()
        and "Phase 10" in phase_9
        and "Out of scope" in phase_9,
        "Phase 9 lacks explicit managed-only handoff and scope separation",
        errors,
    )
    require(
        "synthetic" in phase_10.lower()
        and "managed" in phase_10.lower()
        and "Out of scope" in phase_10,
        "Phase 10 lacks managed synthetic-data ownership",
        errors,
    )
    require(
        "qualified" in phase_11.lower()
        and "promotion" in phase_11.lower()
        and "Out of scope" in phase_11,
        "Phase 11 lacks qualified production-promotion ownership",
        errors,
    )
    shared_frontend = PLAN_DIR / "shared" / "frontend" / "stitch-nextjs-contract.md"
    require(
        shared_frontend.is_file(),
        "Missing shared Phase 7/8 Stitch and Next.js contract",
        errors,
    )
    for path, text in (
        (
            PLAN_DIR / "00-global-contracts.md",
            (PLAN_DIR / "00-global-contracts.md").read_text(encoding="utf-8"),
        ),
        (phase_path(1), phase_1),
        (phase_path(11), phase_11),
    ):
        require(
            "follows Section 10" not in text and "described in Section 10" not in text,
            f"Ambiguous bare legacy Section 10 reference: {path.relative_to(ROOT)}",
            errors,
        )


def validate_navigation(errors: list[str]) -> None:
    """Validate links among current split-plan files.

    Args:
        errors: Mutable error accumulator.
    """

    markdown_paths = [
        ROOT / relative
        for relative in canonical_files()
        if relative.endswith((".md", ".mdc"))
    ]
    link_pattern = re.compile(r"\]\(([^)]+)\)")
    for path in markdown_paths:
        if not path.is_file():
            continue
        for destination in link_pattern.findall(path.read_text(encoding="utf-8")):
            clean = destination.split("#", maxsplit=1)[0]
            if not clean or clean.startswith(("http://", "https://", "../../../")):
                continue
            if clean.endswith("plan-integrity-lock.json"):
                # ``--update`` creates the lock after structural validation.
                continue
            if clean.startswith(("./", "../")):
                target = (path.parent / clean).resolve()
                require(
                    target.exists(),
                    f"Broken plan navigation in {path.relative_to(ROOT)}: {destination}",
                    errors,
                )


def validate_loading_contracts(errors: list[str]) -> None:
    """Validate low-context reading rules and named phase skills.

    Args:
        errors: Mutable error accumulator.
    """

    loading_paths = (
        ROOT / ".cursor" / "plans" / "hybrid-graph-rag_ab5281ef.plan.md",
        ROOT / ".cursor" / "rules" / "00-plan-source-of-truth.mdc",
        ROOT / ".cursor" / "skills" / "implement-plan-phase" / "SKILL.md",
    )
    for path in loading_paths:
        text = path.read_text(encoding="utf-8")
        require(
            "split_source" in text and "exactly one" in text,
            f"Split-source loading contract is incomplete: {repo_relative(path)}",
            errors,
        )
    for relative in BASE_CANONICAL_FILES:
        if not relative.startswith(".cursor/skills/"):
            continue
        skill_text = (ROOT / relative).read_text(encoding="utf-8")
        require(
            "Plan Section" not in skill_text,
            f"Named skill still relies on ambiguous legacy sections: {relative}",
            errors,
        )


def validate_structure() -> list[str]:
    """Run all current-state structural integrity checks.

    Returns:
        List of human-readable errors; empty means success.
    """

    errors: list[str] = []
    for relative in canonical_files():
        require(
            (ROOT / relative).is_file(),
            f"Missing canonical file: {relative}",
            errors,
        )
    if errors:
        return errors
    validate_phase_structure(errors)
    validate_split_packets(errors)
    validate_ownership(errors)
    validate_navigation(errors)
    validate_loading_contracts(errors)
    return errors


def current_hashes() -> dict[str, str]:
    """Hash every canonical file in stable path order.

    Returns:
        Mapping of repository-relative paths to SHA-256 digests.
    """

    return {relative: sha256_file(ROOT / relative) for relative in canonical_files()}


def write_lock() -> None:
    """Write an approved current-state integrity lock.

    Side effects:
        Replaces ``plan-integrity-lock.json`` after structure validation.
    """

    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "files": current_hashes(),
    }
    LOCK_PATH.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def check_lock(errors: list[str]) -> None:
    """Compare current canonical files with the integrity lock.

    Args:
        errors: Mutable error accumulator.
    """

    if not LOCK_PATH.is_file():
        errors.append(f"Missing integrity lock: {LOCK_PATH.relative_to(ROOT)}")
        return
    payload = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    locked = payload.get("files")
    if not isinstance(locked, dict):
        errors.append("Integrity lock has no valid files mapping")
        return
    current = current_hashes()
    if set(locked) != set(current):
        errors.append("Integrity lock file list differs from canonical file list")
        return
    for relative, digest in current.items():
        if locked.get(relative) != digest:
            errors.append(f"Hash mismatch: {relative}")


def main() -> int:
    """Run structural validation and optionally update the hash lock.

    Returns:
        Process exit code: zero on success and one on validation failure.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="Rewrite the lock after all structural checks pass.",
    )
    args = parser.parse_args()

    errors = validate_structure()
    if not errors and args.update:
        write_lock()
    elif not errors:
        check_lock(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    action = "updated" if args.update else "verified"
    print(f"Split plan integrity {action}: {len(canonical_files())} canonical files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
