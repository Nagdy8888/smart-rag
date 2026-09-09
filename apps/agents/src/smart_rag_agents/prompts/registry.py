"""Immutable prompt version registry. Unknown ids fail closed."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from smart_rag_core.settings.base import get_process_environ

_PROMPTS_DIR = Path(__file__).resolve().parent
_ALLOWED_ENVIRONMENTS = frozenset({"dev", "staging", "prod"})
_PROMPT_ENV_VAR = "SMART_RAG_PROMPT_ENV"


class PromptRegistryError(ValueError):
    """Raised when a prompt id is unknown or not promoted to this environment."""


@dataclass(frozen=True, slots=True)
class PromptVersion:
    """One immutable prompt version.

    Attributes:
        prompt_id: Stable version id such as ``summary_v1``.
        path: Markdown file that holds the body.
        sha256: Hex digest of LF-normalized UTF-8 file bytes.
        environments: Environments that may load this version.
    """

    prompt_id: str
    path: Path
    sha256: str
    environments: frozenset[str]


def _sha256_file(path: Path) -> str:
    """Return the LF-normalized SHA-256 hex digest of a prompt file.

    Args:
        path: Prompt markdown path.

    Returns:
        Hex digest.

    Raises:
        PromptRegistryError: When the file is missing.
    """

    if not path.is_file():
        raise PromptRegistryError("prompt_file_missing")
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def _entry(prompt_id: str, filename: str) -> PromptVersion:
    """Build one registry row from a filename.

    Args:
        prompt_id: Version id.
        filename: File under the prompts directory.

    Returns:
        Immutable prompt version.
    """

    path = _PROMPTS_DIR / filename
    return PromptVersion(
        prompt_id=prompt_id,
        path=path,
        sha256=_sha256_file(path),
        environments=frozenset(_ALLOWED_ENVIRONMENTS),
    )


PROMPT_REGISTRY: dict[str, PromptVersion] = {
    "query_profile_v1": _entry("query_profile_v1", "query_profile_v1.md"),
    "rerank_v1": _entry("rerank_v1", "rerank_v1.md"),
    "answer_v1": _entry("answer_v1", "answer_v1.md"),
    "general_chat_v1": _entry("general_chat_v1", "general_chat_v1.md"),
    "verifier_v1": _entry("verifier_v1", "verifier_v1.md"),
    "optional_catalog_v1": _entry("optional_catalog_v1", "optional_catalog_v1.md"),
    "summary_v1": _entry("summary_v1", "summary_v1.md"),
    "eval_judge_v1": _entry("eval_judge_v1", "eval_judge_v1.md"),
    "eval_pdf_judge_v1": _entry("eval_pdf_judge_v1", "eval_pdf_judge_v1.md"),
    "conversation_title_v1": _entry(
        "conversation_title_v1", "conversation_title_v1.md"
    ),
}


def current_prompt_environment() -> str:
    """Return the prompt promotion environment.

    Returns:
        ``dev``, ``staging``, or ``prod``. Default ``dev``.

    Raises:
        PromptRegistryError: When ``SMART_RAG_PROMPT_ENV`` is not allow-listed.
    """

    raw = (get_process_environ(_PROMPT_ENV_VAR, "dev") or "dev").strip().lower()
    if raw not in _ALLOWED_ENVIRONMENTS:
        raise PromptRegistryError("unknown_prompt_environment")
    return raw


def load_prompt(prompt_id: str, *, environment: str | None = None) -> PromptVersion:
    """Load one versioned prompt or fail closed.

    Args:
        prompt_id: Registry key. Every prompt must have a version id.
        environment: Optional override. Default ``SMART_RAG_PROMPT_ENV`` or
            ``dev``.

    Returns:
        Immutable prompt version including sha256.

    Raises:
        PromptRegistryError: Unknown id, missing file, or not promoted.
    """

    if not prompt_id:
        raise PromptRegistryError("prompt_without_version")
    entry = PROMPT_REGISTRY.get(prompt_id)
    if entry is None:
        raise PromptRegistryError("unknown_prompt_id")
    env = environment if environment is not None else current_prompt_environment()
    if env not in entry.environments:
        raise PromptRegistryError("prompt_not_promoted")
    if not entry.path.is_file():
        raise PromptRegistryError("prompt_file_missing")
    digest = _sha256_file(entry.path)
    if digest != entry.sha256:
        raise PromptRegistryError("prompt_sha256_mismatch")
    return entry


def prompt_text(prompt_id: str, *, environment: str | None = None) -> str:
    """Return the markdown body for a versioned prompt.

    Args:
        prompt_id: Registry key.
        environment: Optional promotion environment.

    Returns:
        UTF-8 prompt text.

    Raises:
        PromptRegistryError: Unknown or unpromoted id.
    """

    entry = load_prompt(prompt_id, environment=environment)
    return entry.path.read_text(encoding="utf-8")
