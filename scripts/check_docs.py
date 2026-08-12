#!/usr/bin/env python3
"""Validate documentation presence, local links, and Mermaid rendering."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_ROOT = REPO_ROOT / "docs"
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


@dataclass(frozen=True)
class LinkFailure:
    """Describe one unresolved local Markdown link.

    Attributes:
        document: Markdown file containing the link.
        destination: Unresolved link destination.
    """

    document: Path
    destination: str


def documentation_files() -> list[Path]:
    """Return maintained Markdown documents in stable order.

    Returns:
        Sorted documentation paths.

    Raises:
        FileNotFoundError: If the required ``docs`` directory is absent.
    """

    if not DOCS_ROOT.is_dir():
        raise FileNotFoundError("Required docs directory is missing")
    files = sorted(DOCS_ROOT.rglob("*.md"))
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


def render_mermaid_blocks(documents: list[Path]) -> int:
    """Render every Mermaid block with the pinned CLI.

    Args:
        documents: Markdown documents that may contain diagrams.

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
    with tempfile.TemporaryDirectory(prefix="smart-rag-mermaid-") as temp_name:
        temp_dir = Path(temp_name)
        diagram_number = 0
        for document in documents:
            for block in mermaid_blocks(document):
                diagram_number += 1
                source = temp_dir / f"diagram-{diagram_number}.mmd"
                output = temp_dir / f"diagram-{diagram_number}.svg"
                source.write_text(block, encoding="utf-8")
                completed = subprocess.run(  # noqa: S603 - pinned local pnpm tool
                    (
                        pnpm,
                        "exec",
                        "mmdc",
                        "--input",
                        str(source),
                        "--output",
                        str(output),
                        "--quiet",
                    ),
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


def main() -> int:
    """Run documentation contract checks.

    Returns:
        Zero on success; otherwise a hard failure code.
    """

    try:
        documents = documentation_files()
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
        return render_mermaid_blocks(documents)
    except (FileNotFoundError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
