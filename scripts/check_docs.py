#!/usr/bin/env python3
"""Validate documentation presence, local links, and Mermaid rendering."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
EXCLUDED_DOC_ROOTS = (
    DOCS_ROOT / "prev_review",
    DOCS_ROOT / "stitch_smart_rag_enterprise_console",
)
LINK_PATTERN = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
MERMAID_PATTERN = re.compile(r"```mermaid\s*\n(.*?)```", flags=re.DOTALL)
ALLOWED_MERMAID_KINDS = {
    "erDiagram",
    "flowchart",
    "sequenceDiagram",
    "stateDiagram-v2",
}
PLANNED_MISSING_LINKS = {
    "docs/adr/ADR-embedding-model-dimension.md",
    "docs/adr/ADR-vision-captioning.md",
}
GOVERNANCE_DOCUMENTS = (
    DOCS_ROOT / "security" / "OPENAI_DATA_GOVERNANCE.md",
    DOCS_ROOT / "security" / "SUBPROCESSOR_GOVERNANCE.md",
)
CLAIMED_GOVERNANCE_STATUSES = frozenset({"signed", "verified", "accepted"})
FRONTMATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", flags=re.DOTALL)


@dataclass(frozen=True)
class LinkFailure:
    """Describe one unresolved local Markdown link.

    Attributes:
        document: Markdown file containing the link.
        destination: Unresolved link destination.
    """

    document: Path
    destination: str


@dataclass(frozen=True)
class CheckDocsOptions:
    """Validated documentation-check command-line options.

    Attributes:
        puppeteer_config: Optional explicit Puppeteer launch configuration.
            CI may supply the repository's no-sandbox workaround because
            GitHub-hosted Linux runners disable the required browser sandbox.
    """

    puppeteer_config: Path | None


def parse_options(argv: Sequence[str] | None = None) -> CheckDocsOptions:
    """Parse optional browser-rendering configuration.

    Args:
        argv: Optional argument sequence excluding the program name.

    Returns:
        Validated documentation-check options.
    """

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--puppeteer-config",
        help="Explicit Puppeteer JSON config passed to Mermaid CLI.",
    )
    parsed = parser.parse_args(argv)
    raw_config = cast(str | None, parsed.puppeteer_config)
    return CheckDocsOptions(
        puppeteer_config=Path(raw_config).resolve() if raw_config else None
    )


def documentation_files() -> list[Path]:
    """Return maintained, non-historical Markdown documents in stable order.

    Returns:
        Sorted documentation paths excluding preserved review history and
        generated Stitch source exports.

    Raises:
        FileNotFoundError: If the required ``docs`` directory is absent.
    """

    if not DOCS_ROOT.is_dir():
        raise FileNotFoundError("Required docs directory is missing")
    files = sorted(
        path
        for path in DOCS_ROOT.rglob("*.md")
        if not any(path.is_relative_to(root) for root in EXCLUDED_DOC_ROOTS)
    )
    if not files:
        raise FileNotFoundError("Docs tier collected zero Markdown documents")
    return files


def check_local_links(documents: list[Path]) -> list[LinkFailure]:
    """Resolve local Markdown links while allowing named Packet 5 plans.

    Args:
        documents: Markdown files to inspect.

    Returns:
        Unresolved links excluding the two explicitly planned Phase 1 Packet 5
        ADR targets already identified in Packet 1 evidence.
    """

    failures: list[LinkFailure] = []
    for document in documents:
        text = document.read_text(encoding="utf-8")
        for raw_destination in LINK_PATTERN.findall(text):
            destination = raw_destination.strip().split(maxsplit=1)[0]
            clean = unquote(destination.split("#", maxsplit=1)[0])
            if not clean or clean.startswith(("http://", "https://", "mailto:")):
                continue
            target = (document.parent / clean).resolve()
            if target.exists():
                continue
            try:
                relative_target = target.relative_to(REPO_ROOT).as_posix()
            except ValueError:
                relative_target = str(target)
            if relative_target not in PLANNED_MISSING_LINKS:
                failures.append(LinkFailure(document, destination))
    return failures


def _frontmatter_fields(document: Path) -> dict[str, str]:
    """Parse simple YAML frontmatter key/value pairs from a Markdown file.

    Args:
        document: Markdown path with optional frontmatter.

    Returns:
        Mapping of frontmatter keys to stripped string values. Quoted values
        keep their inner text only.

    Raises:
        ValueError: If claimed governance status lacks required evidence fields.
    """

    text = document.read_text(encoding="utf-8")
    match = FRONTMATTER_PATTERN.match(text)
    if match is None:
        return {}
    fields: dict[str, str] = {}
    for raw_line in match.group(1).splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", maxsplit=1)
        fields[key.strip()] = value.strip().strip("\"'")
    return fields


def check_governance_signoff() -> list[str]:
    """Reject signed/verified/accepted governance docs without approver evidence.

    Returns:
        Human-readable error strings. Empty when both governance documents carry
        approver, approval date, policy version, and real-content posture.

    Side Effects:
        None.
    """

    errors: list[str] = []
    required = (
        "approver",
        "approval_date",
        "policy_version",
        "real_company_content_external_processing",
    )
    for document in GOVERNANCE_DOCUMENTS:
        try:
            relative = document.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            relative = document.as_posix()
        if not document.is_file():
            errors.append(f"missing governance document {relative}")
            continue
        fields = _frontmatter_fields(document)
        status = fields.get("status", "").lower()
        if status not in CLAIMED_GOVERNANCE_STATUSES:
            continue
        for key in required:
            if not fields.get(key):
                errors.append(
                    f"{relative} claims status={status!r} without required "
                    f"frontmatter field {key!r}"
                )
        posture = fields.get("real_company_content_external_processing", "").lower()
        if posture not in {"prohibited", "allowed"}:
            errors.append(
                f"{relative} must set real_company_content_external_processing "
                "to prohibited or allowed"
            )
    return errors


def mermaid_blocks(document: Path) -> list[str]:
    """Extract and minimally classify Mermaid source blocks.

    Args:
        document: Markdown file to inspect.

    Returns:
        Mermaid source blocks.

    Raises:
        ValueError: If a block is empty or uses a disallowed diagram kind.
    """

    blocks = MERMAID_PATTERN.findall(document.read_text(encoding="utf-8"))
    for index, block in enumerate(blocks, start=1):
        first_line = next(
            (line.strip() for line in block.splitlines() if line.strip()),
            "",
        )
        kind = first_line.split(maxsplit=1)[0] if first_line else ""
        if kind not in ALLOWED_MERMAID_KINDS:
            raise ValueError(
                f"{document.relative_to(REPO_ROOT)} Mermaid block {index} "
                f"has unsupported or empty kind {kind!r}"
            )
    return blocks


def render_mermaid_blocks(
    documents: list[Path],
    puppeteer_config: Path | None = None,
) -> int:
    """Render every Mermaid block with the pinned CLI.

    Args:
        documents: Markdown documents that may contain diagrams.
        puppeteer_config: Optional Puppeteer launch configuration supplied by
            the caller. Local runs retain the browser sandbox by default.

    Returns:
        Zero when every diagram renders; otherwise the exact Mermaid child exit
        code, or 127 when pnpm is unavailable.

    Side Effects:
        Creates temporary Mermaid and SVG files, then removes them.
    """

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        print("ERROR: pnpm is required for Mermaid rendering", file=sys.stderr)
        return 127
    if puppeteer_config is not None and not puppeteer_config.is_file():
        raise FileNotFoundError(
            f"Puppeteer configuration is missing: {puppeteer_config}"
        )
    with tempfile.TemporaryDirectory(prefix="smart-rag-mermaid-") as temp_name:
        temp_dir = Path(temp_name)
        diagram_number = 0
        for document in documents:
            for block in mermaid_blocks(document):
                diagram_number += 1
                source = temp_dir / f"diagram-{diagram_number}.mmd"
                output = temp_dir / f"diagram-{diagram_number}.svg"
                source.write_text(block, encoding="utf-8")
                command = [
                    pnpm,
                    "exec",
                    "mmdc",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                    "--quiet",
                ]
                if puppeteer_config is not None:
                    command.extend(("--puppeteerConfigFile", str(puppeteer_config)))
                completed = subprocess.run(  # noqa: S603 - pinned local pnpm tool
                    tuple(command),
                    cwd=REPO_ROOT,
                    check=False,
                )
                if completed.returncode != 0:
                    return completed.returncode
                if not output.is_file():
                    print(
                        f"ERROR: Mermaid produced no output for {source.name}",
                        file=sys.stderr,
                    )
                    return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run documentation contract checks.

    Args:
        argv: Optional argument sequence excluding the program name.

    Returns:
        Zero on success; otherwise a hard failure code.
    """

    options = parse_options(argv)
    try:
        documents = documentation_files()
        governance_errors = check_governance_signoff()
        if governance_errors:
            for message in governance_errors:
                print(f"ERROR: {message}", file=sys.stderr)
            return 1
        failures = check_local_links(documents)
        if failures:
            for failure in failures:
                print(
                    "ERROR: broken link "
                    f"{failure.document.relative_to(REPO_ROOT)} -> "
                    f"{failure.destination}",
                    file=sys.stderr,
                )
            return 1
        return render_mermaid_blocks(documents, options.puppeteer_config)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
