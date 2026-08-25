"""Unit tests for old-API / current-schema drain smoke classification."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from smart_rag_core.release.constants import OLD_API_IMAGE_ENV
from smart_rag_core.release.old_api_smoke import (
    MIN_CLIENT_VERSION,
    OldApiSlotHooks,
    OldApiSmokeOutcome,
    apply_outcome_to_handoff_row,
    evaluate_old_api_new_schema_smoke,
    execute_authenticated_smoke,
    ids_equal,
    normalize_image_id,
    upload_status_ok,
)
from smart_rag_core.release.packet2 import (
    HANDOFFS,
    PACKET1_EXPECTED_IMAGE_IDS,
    PYTEST_SUITES,
    pytest_spec_path,
)
from smart_rag_core.release.packet7 import LOCAL_BLOCKERS, with_old_api_smoke

FREEZE = PACKET1_EXPECTED_IMAGE_IDS["api"]
PRIOR = "sha256:" + ("ab" * 32)
REPO_ROOT = Path(__file__).resolve().parents[2]
SMOKE_SOURCE = (
    REPO_ROOT
    / "packages"
    / "core"
    / "src"
    / "smart_rag_core"
    / "release"
    / "old_api_smoke.py"
)


def _inspect_fail(reference: str) -> str | None:
    """Raise if inspect is invoked."""

    del reference
    raise AssertionError("old-API smoke hook must not run")


def _inspect_none(reference: str) -> str | None:
    """Pretend the image is missing."""

    del reference
    return None


def _inspect_freeze(reference: str) -> str | None:
    """Resolve every reference to the Packet 1 freeze."""

    del reference
    return FREEZE


def _inspect_prior(reference: str) -> str | None:
    """Resolve every reference to the synthetic prior Id."""

    del reference
    return PRIOR


def _recreate_fail(image_id: str) -> str | None:
    """Raise if Compose recreate is invoked."""

    del image_id
    raise AssertionError("old-API smoke hook must not run")


def _http_fail() -> tuple[bool, str]:
    """Raise if HTTP smoke is invoked."""

    raise AssertionError("old-API smoke hook must not run")


def test_old_api_smoke_is_not_a_pytest_suite() -> None:
    """Packet 2 must not collect this gate as skippable pytest."""

    specs = [
        pytest_spec_path(spec)
        for suite in PYTEST_SUITES
        for spec in (*suite.pytest_args, *suite.deselect)
    ]
    assert not any("old_api" in spec for spec in specs)
    source = SMOKE_SOURCE.read_text(encoding="utf-8")
    assert "pytest.skip(" not in source
    runner = REPO_ROOT / "scripts" / "ci" / "check_old_api_new_schema_smoke.py"
    assert "pytest.skip(" not in runner.read_text(encoding="utf-8")


def test_missing_env_is_blocked_and_does_not_run_hooks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Unset SMART_RAG_OLD_API_IMAGE is Blocked, not Passed or skipped."""

    monkeypatch.delenv(OLD_API_IMAGE_ENV, raising=False)
    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_fail,
            recreate_api=_recreate_fail,
            http_smoke=_http_fail,
        ),
        write_artifact=False,
    )
    assert outcome.classification == "Blocked"
    assert outcome.smoke_ran is False
    assert outcome.restored_freeze is False
    assert OLD_API_IMAGE_ENV in outcome.reason
    assert "Do not fake" in outcome.next_action
    static = next(row for row in HANDOFFS if row.item_id == "old_api_new_schema_smoke")
    assert static.managed_only is False
    assert static.classification == "Passed"


def test_blank_env_is_blocked(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Whitespace-only env is treated as missing."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, "   ")
    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_fail,
            recreate_api=_recreate_fail,
            http_smoke=_http_fail,
        ),
        write_artifact=False,
    )
    assert outcome.classification == "Blocked"
    assert outcome.smoke_ran is False


def test_freeze_image_env_is_failed_without_inspect(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The Packet 1 freeze Id cannot be used as a prior slot."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, FREEZE)
    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_fail,
            recreate_api=_recreate_fail,
            http_smoke=_http_fail,
        ),
        write_artifact=False,
    )
    assert outcome.classification == "Failed"
    assert outcome.smoke_ran is False
    assert "Packet 1 freeze" in outcome.reason


def test_tag_resolving_to_freeze_is_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A tag that inspects to the freeze Id is still a fake pass."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, "smart-rag-api:yesterday")
    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_freeze,
            recreate_api=_recreate_fail,
            http_smoke=_http_fail,
        ),
        write_artifact=False,
    )
    assert outcome.classification == "Failed"
    assert outcome.smoke_ran is False


def test_missing_local_image_is_blocked(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A prior digest that docker cannot inspect stays Blocked."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, PRIOR)
    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_none,
            recreate_api=_recreate_fail,
            http_smoke=_http_fail,
        ),
        write_artifact=False,
    )
    assert outcome.classification == "Blocked"
    assert outcome.smoke_ran is False
    assert "docker inspect" in outcome.reason


def test_live_smoke_passes_then_restores_freeze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A distinct prior image is smoked, then the freeze slot is restored."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, PRIOR)
    seen: list[str] = []

    def _recreate(image_id: str) -> str:
        """Record one API slot recreate.

        Args:
            image_id: Image digest placed in the API slot.

        Returns:
            The same image id.
        """

        seen.append(image_id)
        return image_id

    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_prior,
            recreate_api=_recreate,
            http_smoke=lambda: (True, "ok"),
        ),
        write_artifact=True,
    )
    assert seen == [PRIOR, FREEZE]
    assert outcome.classification == "Passed"
    assert outcome.smoke_ran is True
    assert outcome.restored_freeze is True
    artifact = (
        tmp_path
        / "docs"
        / "deployment"
        / "phase-09"
        / "candidate-old-api-new-schema-smoke.json"
    )
    assert artifact.is_file()
    text = artifact.read_text(encoding="utf-8")
    assert "Passed" in text
    assert FREEZE in text
    assert PRIOR in text


def test_http_failure_still_restores_freeze(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failed HTTP smoke must still put the freeze API back."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, PRIOR)
    seen: list[str] = []

    def _recreate(image_id: str) -> str:
        """Record one API slot recreate.

        Args:
            image_id: Image digest placed in the API slot.

        Returns:
            The same image id.
        """

        seen.append(image_id)
        return image_id

    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_prior,
            recreate_api=_recreate,
            http_smoke=lambda: (False, "authenticated GET /me failed"),
        ),
        write_artifact=False,
    )
    assert seen == [PRIOR, FREEZE]
    assert outcome.classification == "Failed"
    assert outcome.smoke_ran is True
    assert outcome.restored_freeze is True


def test_restore_failure_is_failed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Leaving the stack on the old slot after smoke is Failed."""

    monkeypatch.setenv(OLD_API_IMAGE_ENV, PRIOR)

    def _recreate(image_id: str) -> str | None:
        """Fail when restoring the freeze image.

        Args:
            image_id: Requested slot image.

        Returns:
            The prior image, or ``None`` when freeze restore is requested.
        """

        if ids_equal(image_id, FREEZE):
            return None
        return PRIOR

    outcome = evaluate_old_api_new_schema_smoke(
        tmp_path,
        freeze_api_id=FREEZE,
        hooks=OldApiSlotHooks(
            inspect_image_id=_inspect_prior,
            recreate_api=_recreate,
            http_smoke=lambda: (True, "ok"),
        ),
        write_artifact=False,
    )
    assert outcome.classification == "Failed"
    assert outcome.restored_freeze is False
    assert "not restored" in outcome.reason


def test_authenticated_http_smoke_accepts_read_chat_upload() -> None:
    """Mocked FastAPI accepts /me, chat, and upload (200 or 403)."""

    conversation_id = "11111111-1111-1111-1111-111111111111"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve compatible old-slot HTTP responses.

        Args:
            request: Incoming mock request.

        Returns:
            Status 200/201/202/403 for supported paths, otherwise 404.
        """

        path = request.url.path
        if path == "/health/live":
            return httpx.Response(200, json={"status": "live"})
        if path == "/me":
            return httpx.Response(200, json={"user_id": "u1", "role": "member"})
        if path == "/documents":
            return httpx.Response(200, json=[])
        if path == "/conversations" and request.method == "POST":
            return httpx.Response(201, json={"conversation_id": conversation_id})
        if path.endswith("/messages"):
            assert request.headers.get("X-Client-Version") == MIN_CLIENT_VERSION
            return httpx.Response(202, json={"run_id": "r1"})
        if path == "/documents/uploads":
            return httpx.Response(403, json={"detail": "forbidden"})
        return httpx.Response(404, json={"detail": "missing"})

    transport = httpx.MockTransport(_handler)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        ok, reason, steps = execute_authenticated_smoke(
            api_base="http://old-api.test",
            access_token="unit-test-bearer",  # noqa: S106
            client=client,
        )
    assert ok is True
    assert "read/chat/upload" in reason
    names = [step.name for step in steps]
    assert names == [
        "live",
        "read_me",
        "read_documents",
        "chat_create",
        "chat_message",
        "upload",
    ]
    assert all(step.ok for step in steps)


def test_authenticated_http_smoke_rejects_unauth_upload() -> None:
    """HTTP 401 on upload is not a compatible old-slot response."""

    conversation_id = "11111111-1111-1111-1111-111111111111"

    def _handler(request: httpx.Request) -> httpx.Response:
        """Serve an unauthorized upload response.

        Args:
            request: Incoming mock request.

        Returns:
            Compatible reads plus HTTP 401 on upload.
        """

        path = request.url.path
        if path == "/health/live":
            return httpx.Response(200, json={"status": "live"})
        if path == "/me":
            return httpx.Response(200, json={"user_id": "u1"})
        if path == "/documents":
            return httpx.Response(200, json=[])
        if path == "/conversations":
            return httpx.Response(201, json={"conversation_id": conversation_id})
        if path.endswith("/messages"):
            return httpx.Response(202, json={"run_id": "r1"})
        if path == "/documents/uploads":
            return httpx.Response(401, json={"detail": "unauthenticated"})
        return httpx.Response(404)

    transport = httpx.MockTransport(_handler)
    with httpx.Client(transport=transport, timeout=5.0) as client:
        ok, reason, steps = execute_authenticated_smoke(
            api_base="http://old-api.test",
            access_token="unit-test-bearer",  # noqa: S106
            client=client,
        )
    assert ok is False
    assert "uploads" in reason
    assert steps[-1].name == "upload"
    assert steps[-1].ok is False
    assert upload_status_ok(403) is True
    assert upload_status_ok(200) is True
    assert upload_status_ok(401) is False


def test_packet7_overlay_uses_live_classification() -> None:
    """Packet 7 local blockers consume the harness instead of a static skip."""

    outcome = OldApiSmokeOutcome(
        classification="Failed",
        reason="SMART_RAG_OLD_API_IMAGE resolved to the Packet 1 freeze API Id.",
        next_action="Point SMART_RAG_OLD_API_IMAGE at a prior digest.",
        freeze_api_id=FREEZE,
        requested=FREEZE,
        resolved_image_id=FREEZE,
        smoke_ran=False,
        restored_freeze=False,
    )
    overlaid = with_old_api_smoke(
        outcome.classification,
        outcome.reason,
        outcome.next_action,
    )
    item = next(row for row in overlaid if row.item_id == "old_api_new_schema_smoke")
    assert item.classification == "Failed"
    assert item.local_launch_blocking is True
    static = next(
        row for row in LOCAL_BLOCKERS if row.item_id == "old_api_new_schema_smoke"
    )
    assert static.classification == "Passed"
    row = apply_outcome_to_handoff_row(
        {
            "item_id": "old_api_new_schema_smoke",
            "classification": "Blocked",
            "reason": "old",
            "next_action": "old",
        },
        outcome,
    )
    assert row["classification"] == "Failed"


def test_normalize_image_id_accepts_bare_hex() -> None:
    """64-hex values gain a sha256 prefix and lowercase."""

    hex_id = "AB" * 32
    assert normalize_image_id(hex_id) == "sha256:" + ("ab" * 32)
    assert ids_equal("sha256:" + ("ab" * 32), hex_id)
