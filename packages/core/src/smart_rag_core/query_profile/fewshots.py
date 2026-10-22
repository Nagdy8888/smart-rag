"""Approved few-shot manifest. Holdout case ids are never admitted."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from smart_rag_core.query_profile.versions import PROFILE_PROMPT_VERSION

REPO_ROOT = Path(__file__).resolve().parents[5]
DEFAULT_FEWSHOT_PATH = (
    REPO_ROOT / "tests" / "fixtures" / "evaluation" / "phase4" / "fewshots-v3.json"
)
HOLDOUT_MANIFEST_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "evaluation"
    / "phase4"
    / "manifests"
    / "holdout.json"
)


class FewShotManifestError(ValueError):
    """Raised when a few-shot manifest is missing, leaked, or holdout-tainted."""


class FewShotManifest(BaseModel):
    """SME-approved few-shot case ids for the profile prompt.

    Attributes:
        version: Manifest version.
        prompt_version: Prompt these few-shots are bound to.
        approved_case_ids: Development/qualification ids only. Empty until SME
            approval. Holdout ids are forbidden.
        notes: Human-readable status.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str = Field(min_length=3, max_length=64)
    prompt_version: str = Field(min_length=3, max_length=64)
    approved_case_ids: tuple[str, ...] = ()
    notes: str = ""

    @model_validator(mode="after")
    def _prompt_matches(self) -> FewShotManifest:
        """Reject few-shots bound to a different prompt version.

        Returns:
            The manifest.

        Raises:
            ValueError: If the prompt version does not match Packet 3.
        """

        if self.prompt_version != PROFILE_PROMPT_VERSION:
            raise ValueError("fewshot_prompt_version_mismatch")
        return self


def holdout_case_ids(path: Path | None = None) -> frozenset[str]:
    """Return sealed holdout ids from the id/hash manifest.

    Args:
        path: Optional override. Default is the Packet 1 holdout manifest.

    Returns:
        Holdout case ids. Query text is not present in that file.
    """

    payload = json.loads((path or HOLDOUT_MANIFEST_PATH).read_text(encoding="utf-8"))
    return frozenset(str(item) for item in payload["case_ids"])


def load_fewshot_manifest(path: Path | None = None) -> FewShotManifest:
    """Load and validate the approved few-shot manifest.

    Args:
        path: Optional override path.

    Returns:
        Frozen manifest.

    Raises:
        FewShotManifestError: If a holdout id is listed or JSON is invalid.
    """

    target = path or DEFAULT_FEWSHOT_PATH
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        manifest = FewShotManifest.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise FewShotManifestError("invalid_fewshot_manifest") from error
    blocked = holdout_case_ids().intersection(manifest.approved_case_ids)
    if blocked:
        raise FewShotManifestError("holdout_fewshot_forbidden")
    return manifest
