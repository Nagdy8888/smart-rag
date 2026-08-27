"""Shared LangSmith tracing context and production-file scanners."""

from __future__ import annotations

import ast
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import cast

import langsmith

from tests.unit.typed_attrs import module_attr

REPO_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_OPENAI_CTOR = {
    Path("packages/core/src/smart_rag_core/observability/langsmith_tracing.py"),
}

ALLOWED_RESPONSES_CREATE = {
    Path("packages/core/src/smart_rag_core/gateways/openai_rerank.py"),
    Path("packages/core/src/smart_rag_core/gateways/openai_answer.py"),
    Path("packages/core/src/smart_rag_core/gateways/openai_lightrag.py"),
    Path("packages/core/src/smart_rag_core/gateways/openai_general_chat.py"),
    Path("packages/core/src/smart_rag_core/gateways/openai_profile.py"),
}

ALLOWED_EMBEDDINGS_CREATE = {
    Path("packages/core/src/smart_rag_core/observability/langsmith_tracing.py"),
}

_SCAN_ROOTS = (
    Path("packages"),
    Path("apps"),
    Path("scripts"),
)

CANARY_TOKEN = "sk-canarysecretFORBID123456"  # noqa: S105 - inert leak canary

CANARY_EMAIL = "canary.user@example.com"

CANARY_PASSAGE = "SECRET_COMPANY_PASSAGE_DO_NOT_EXPORT"


def tracing_context_source(
    *, enabled: bool, client: object
) -> AbstractContextManager[object]:
    """Return LangSmith ``tracing_context`` with a known callable type.

    Args:
        enabled: Whether tracing is enabled for the block.
        client: Recording client used by the unit tests.

    Returns:
        Context manager from ``langsmith.tracing_context``.
    """

    factory = cast(
        Callable[..., AbstractContextManager[object]],
        module_attr(langsmith, "tracing_context"),
    )
    return factory(enabled=enabled, client=client)


def scanned_python_files() -> tuple[Path, ...]:
    """Return authored production Python files under packages, apps, and scripts.

    Returns:
        Sorted relative paths.
    """

    files: list[Path] = []
    for root in _SCAN_ROOTS:
        files.extend(
            path.relative_to(REPO_ROOT)
            for path in (REPO_ROOT / root).rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return tuple(sorted(files))


def call_name(node: ast.AST) -> str | None:
    """Return a dotted call name when the callee is a Name or Attribute.

    Args:
        node: AST node, expected to be ``ast.Call``.

    Returns:
        Dotted name such as ``OpenAI`` or ``client.embeddings.create``.
    """

    if not isinstance(node, ast.Call):
        return None
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
        return ".".join(reversed(parts))
    return None
