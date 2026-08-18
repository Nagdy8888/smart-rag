"""Bounded old-API / current-schema drain smoke for Phase 9 Packet 2/7.

The Packet 1 freeze API Id is never a valid prior slot. Missing
``SMART_RAG_OLD_API_IMAGE`` or a missing local image classifies Blocked
(fail-closed). This module is not a pytest skip path.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from uuid import uuid4

import httpx
import psycopg

from smart_rag_core.release.compose import inspect_image, run_compose
from smart_rag_core.release.constants import (
    ARTIFACT_DIR,
    OLD_API_IMAGE_ENV,
    OLD_API_SMOKE_ARTIFACT,
    OLD_API_SMOKE_SCHEMA_VERSION,
    TMP_SCAN_DIR,
)
from smart_rag_core.release.errors import CandidateReleaseError
from smart_rag_core.release.io import as_json_object, dump_canonical_json
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.settings.base import get_process_environ

SHA256_IMAGE_ID = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
DEFAULT_API_BASE = "http://127.0.0.1:8000"
DEFAULT_SUPABASE_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
MIN_CLIENT_VERSION = "0.1.0"
_SMOKE_PASSWORD = "OldApiSmoke9x"  # noqa: S105 - disposable local Auth user
MISSING_ENV_REASON = (
    "SMART_RAG_OLD_API_IMAGE is unset. No prior expand-compatible API "
    "digest exists to smoke against the current schema."
)
MISSING_IMAGE_REASON = (
    "SMART_RAG_OLD_API_IMAGE is set but docker inspect cannot resolve a "
    "local image. Keep a prior expand-compatible API digest."
)
FREEZE_REASON = (
    "SMART_RAG_OLD_API_IMAGE resolved to the Packet 1 freeze API Id. "
    "Do not fake this with the single Packet 1 candidate image."
)
MISSING_ENV_NEXT = (
    "Set SMART_RAG_OLD_API_IMAGE to a prior expand-compatible API image "
    "Id, keep that image locally, and re-run authenticated "
    "read/chat/upload smoke. Do not fake this with the single Packet 1 "
    "candidate image."
)
FREEZE_NEXT = (
    "Point SMART_RAG_OLD_API_IMAGE at a prior expand-compatible API "
    "digest, not the current Packet 1 freeze, then re-run the smoke."
)
MISSING_IMAGE_NEXT = (
    "Load the prior API image locally (today's freeze becomes "
    "yesterday's image after a rebuild) and re-run the smoke. Do not "
    "fake this with the single Packet 1 candidate image."
)


class ImageIdInspector(Protocol):
    """Resolve a Docker image reference to an image Id."""

    def __call__(self, reference: str) -> str | None:
        """Return a normalized ``sha256:`` Id, or ``None`` when missing."""


@dataclass(frozen=True, slots=True)
class OldApiSlotHooks:
    """Injected Docker/HTTP boundary for unit tests.

    Attributes:
        inspect_image_id: Resolve a reference to an image Id.
        recreate_api: Recreate the ``api`` service as ``image_id`` and
            return the running image Id.
        http_smoke: Run authenticated read/chat/upload. Returns ok plus
            a secret-free reason.
    """

    inspect_image_id: ImageIdInspector
    recreate_api: Callable[[str], str | None]
    http_smoke: Callable[[], tuple[bool, str]]


@dataclass(frozen=True, slots=True)
class SmokeStep:
    """One HTTP probe without response bodies.

    Attributes:
        name: Stable step id.
        status_code: HTTP status, or ``None`` on transport failure.
        ok: Whether the status is accepted for that step.
    """

    name: str
    status_code: int | None
    ok: bool


@dataclass(frozen=True, slots=True)
class OldApiSmokeOutcome:
    """Fail-closed Packet 2/7 classification for the drain smoke.

    Attributes:
        classification: ``Blocked``, ``Failed``, or ``Passed``.
        reason: Secret-free explanation.
        next_action: Follow-up for Packet 7.
        freeze_api_id: Packet 1 API image Id.
        requested: Raw env value after strip, or ``None``.
        resolved_image_id: Inspected prior image Id when known.
        smoke_ran: True only after HTTP probes against the prior image.
        restored_freeze: True when the freeze API slot was restored.
        steps: HTTP step summaries.
    """

    classification: Classification
    reason: str
    next_action: str
    freeze_api_id: str
    requested: str | None
    resolved_image_id: str | None
    smoke_ran: bool
    restored_freeze: bool
    steps: tuple[SmokeStep, ...] = ()


def normalize_image_id(value: str) -> str:
    """Normalize a Docker image Id or leave a tag unchanged.

    Args:
        value: Image Id, digest, or name:tag.

    Returns:
        ``sha256:`` plus lowercase hex when the value is a 64-hex digest;
        otherwise the stripped original reference.
    """

    stripped = value.strip().strip("\"'")
    match = SHA256_IMAGE_ID.fullmatch(stripped)
    if match:
        return f"sha256:{match.group(1).lower()}"
    return stripped


def read_old_api_image_env() -> str | None:
    """Return ``SMART_RAG_OLD_API_IMAGE`` through the settings boundary.

    Returns:
        Stripped value, or ``None`` when unset or blank.
    """

    raw = get_process_environ(OLD_API_IMAGE_ENV)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def ids_equal(left: str, right: str) -> bool:
    """Return whether two image references name the same digest.

    Args:
        left: First image Id or digest.
        right: Second image Id or digest.

    Returns:
        True when both normalize to the same ``sha256:`` Id.
    """

    return normalize_image_id(left) == normalize_image_id(right)


def docker_inspect_image_id(reference: str) -> str | None:
    """Resolve one local image reference via ``docker inspect``.

    Args:
        reference: Image Id, digest, or tag.

    Returns:
        Normalized image Id, or ``None`` when inspect fails.
    """

    try:
        payload = inspect_image(reference)
    except CandidateReleaseError:
        return None
    image_id = payload.get("Id")
    if not isinstance(image_id, str) or not image_id:
        return None
    return normalize_image_id(image_id)


def running_api_image_id(repo_root: Path) -> str | None:
    """Return the running Compose ``api`` container image Id.

    Args:
        repo_root: Repository root.

    Returns:
        Normalized image Id, or ``None`` when the container is missing.
    """

    ps = run_compose(repo_root, ["ps", "-q", "api"], timeout_seconds=30)
    lines = [line.strip() for line in (ps.stdout or "").splitlines() if line.strip()]
    if ps.returncode != 0 or not lines:
        return None
    try:
        payload = inspect_image(lines[0])
    except CandidateReleaseError:
        return None
    image = payload.get("Image")
    if not isinstance(image, str) or not image:
        return None
    return normalize_image_id(image)


def recreate_api_with_image(repo_root: Path, image_id: str) -> str | None:
    """Recreate only the ``api`` service from an explicit image Id.

    Uses a temporary Compose overlay. Candidate ``docker-compose.yml`` is
    unchanged. Packet 8 overlay is not attached. The freeze must be
    restored by a later call with the Packet 1 API Id.

    Args:
        repo_root: Repository root.
        image_id: Docker image Id to run.

    Returns:
        Running image Id after ``--wait``, or ``None`` on failure.

    Side Effects:
        Writes then deletes ``.tmp-phase09/old-api-slot.yml`` and
        force-recreates the ``api`` container with ``--no-build``.
    """

    overlay = repo_root / TMP_SCAN_DIR / "old-api-slot.yml"
    overlay.parent.mkdir(parents=True, exist_ok=True)
    overlay.write_text(
        f"services:\n  api:\n    image: {normalize_image_id(image_id)}\n",
        encoding="utf-8",
    )
    try:
        completed = run_compose(
            repo_root,
            [
                "-f",
                str(overlay),
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--wait",
                "--force-recreate",
                "api",
            ],
            timeout_seconds=180,
        )
    finally:
        overlay.unlink(missing_ok=True)
    if completed.returncode != 0:
        return None
    return running_api_image_id(repo_root)


def api_base_url() -> str:
    """Return the host FastAPI origin from ``API_HOST_PORT`` when set.

    Returns:
        ``http://127.0.0.1:{port}``.
    """

    port = get_process_environ("API_HOST_PORT") or "8000"
    return f"http://127.0.0.1:{port.strip() or '8000'}"


def upload_status_ok(status_code: int) -> bool:
    """Return whether an authenticated upload status is accepted.

    ``200`` reserves. ``403`` is an authorized denial (no upload or MFA).
    ``401``/``404``/``5xx`` are not a schema-compatible smoke.

    Args:
        status_code: HTTP status from ``POST /documents/uploads``.

    Returns:
        True when the old API handled the current upload route.
    """

    return status_code in {200, 403}


def execute_authenticated_smoke(
    *,
    api_base: str,
    access_token: str,
    client: httpx.Client,
    client_version: str = MIN_CLIENT_VERSION,
) -> tuple[bool, str, tuple[SmokeStep, ...]]:
    """Probe authenticated read, chat, and upload on one API origin.

    Args:
        api_base: FastAPI origin, no trailing slash.
        access_token: Bearer JWT. Callers must not log it.
        client: Shared HTTP client.
        client_version: ``X-Client-Version`` for paid chat/upload.

    Returns:
        ``(ok, reason, steps)``. Reason never includes tokens.
    """

    auth = f"Bearer {access_token}"
    get_headers = {
        "Authorization": auth,
        "Accept": "application/json",
    }
    post_headers = {
        **get_headers,
        "Content-Type": "application/json",
        "X-Client-Version": client_version,
    }
    steps: list[SmokeStep] = []

    def probe(
        name: str,
        method: str,
        path: str,
        *,
        accepted: set[int],
        json_body: dict[str, object] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> bool:
        """Run one HTTP call and append a secret-free step."""

        headers = dict(post_headers if method != "GET" else get_headers)
        if name == "live":
            headers = {"Accept": "application/json"}
        if extra_headers:
            headers.update(extra_headers)
        try:
            response = client.request(
                method,
                f"{api_base}{path}",
                headers=headers,
                json=json_body,
            )
            status_code = response.status_code
        except httpx.HTTPError:
            steps.append(SmokeStep(name=name, status_code=None, ok=False))
            return False
        ok = status_code in accepted
        steps.append(SmokeStep(name=name, status_code=status_code, ok=ok))
        return ok

    if not probe("live", "GET", "/health/live", accepted={200}):
        return False, "old API /health/live failed", tuple(steps)
    if not probe("read_me", "GET", "/me", accepted={200}):
        return False, "authenticated GET /me failed", tuple(steps)
    if not probe("read_documents", "GET", "/documents", accepted={200}):
        return False, "authenticated GET /documents failed", tuple(steps)
    title = f"old-api-smoke-{uuid4().hex[:12]}"
    try:
        created = client.post(
            f"{api_base}/conversations",
            headers=post_headers,
            json={"title": title},
        )
        created_status = created.status_code
    except httpx.HTTPError:
        steps.append(SmokeStep(name="chat_create", status_code=None, ok=False))
        return False, "POST /conversations transport failed", tuple(steps)
    create_ok = created_status == 201
    steps.append(
        SmokeStep(name="chat_create", status_code=created_status, ok=create_ok)
    )
    if not create_ok:
        return False, "authenticated POST /conversations failed", tuple(steps)
    try:
        created_body: object = created.json()
        body_map = as_json_object(created_body, source="conversations.create")
    except (ValueError, TypeError):
        return False, "POST /conversations returned non-JSON", tuple(steps)
    conversation_id = body_map.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
        return False, "POST /conversations omitted conversation_id", tuple(steps)
    chat_key = str(uuid4())
    if not probe(
        "chat_message",
        "POST",
        f"/conversations/{conversation_id}/messages",
        accepted={202},
        json_body={"message": "old-api schema smoke", "idempotency_key": chat_key},
        extra_headers={"Idempotency-Key": chat_key},
    ):
        return False, "authenticated POST /messages failed", tuple(steps)
    upload_key = f"upload-{uuid4()}"
    if not probe(
        "upload",
        "POST",
        "/documents/uploads",
        accepted={200, 403},
        json_body={"declared_bytes": 1024, "idempotency_key": upload_key},
        extra_headers={"Idempotency-Key": upload_key},
    ):
        return False, "authenticated POST /documents/uploads failed", tuple(steps)
    return True, "authenticated read/chat/upload accepted", tuple(steps)


def _supabase_status(repo_root: Path) -> dict[str, str] | None:
    """Return local ``supabase status -o json`` keys without logging them.

    Args:
        repo_root: Repository root.

    Returns:
        Status mapping, or ``None`` when the CLI is unavailable.
    """

    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return None
    try:
        completed = subprocess.run(  # noqa: S603
            [pnpm, "exec", "supabase", "status", "-o", "json"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    try:
        loaded: object = json.loads(completed.stdout)
        status_map = as_json_object(loaded, source="supabase status")
    except (json.JSONDecodeError, ValueError):
        return None
    out: dict[str, str] = {}
    for key, value in status_map.items():
        if isinstance(value, str):
            out[key] = value
    return out or None


def _upsert_member_profile(db_url: str, user_id: str) -> None:
    """Insert or update the smoke user's ``app.profiles`` row.

    Args:
        db_url: Local Postgres URL. Never logged.
        user_id: Auth user UUID.

    Raises:
        psycopg.Error: If the profile write fails.
    """

    with psycopg.connect(db_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO app.profiles (
                  user_id, role, upload_enabled, mfa_enrolled, monthly_llm_budget_usd
                )
                VALUES (%s, 'member'::app.user_role, false, false, 100)
                ON CONFLICT (user_id) DO UPDATE
                  SET role = 'member'::app.user_role,
                      upload_enabled = false,
                      mfa_enrolled = false
                """,
                (user_id,),
            )
        connection.commit()


def issue_smoke_access_token(repo_root: Path) -> str | None:
    """Create a disposable local Auth user and return a password JWT.

    Args:
        repo_root: Repository root for ``supabase status``.

    Returns:
        Access token, or ``None`` when Auth bootstrap fails.

    Side Effects:
        Creates one confirmed Auth user and an ``app.profiles`` row.
        Credentials are not written to artifacts.
    """

    status = _supabase_status(repo_root)
    if status is None:
        return None
    anon = status.get("ANON_KEY") or status.get("PUBLISHABLE_KEY")
    service = status.get("SERVICE_ROLE_KEY")
    auth_url = (status.get("API_URL") or "http://127.0.0.1:54321").rstrip("/")
    if not anon or not service:
        return None
    db_url = get_process_environ("SUPABASE_DB_URL") or DEFAULT_SUPABASE_DB_URL
    email = f"old-api-smoke-{uuid4().hex}@example.com"
    try:
        with httpx.Client(timeout=15.0) as client:
            created = client.post(
                f"{auth_url}/auth/v1/admin/users",
                headers={
                    "Authorization": f"Bearer {service}",
                    "apikey": service,
                },
                json={
                    "email": email,
                    "password": _SMOKE_PASSWORD,
                    "email_confirm": True,
                },
            )
            if created.status_code >= 400:
                return None
            try:
                created_payload: object = created.json()
                payload_map = as_json_object(
                    created_payload, source="auth admin create"
                )
            except (ValueError, TypeError):
                return None
            user_raw = payload_map.get("id")
            if not isinstance(user_raw, str) or not user_raw:
                return None
            _upsert_member_profile(db_url, user_raw)
            token_response = client.post(
                f"{auth_url}/auth/v1/token?grant_type=password",
                headers={"apikey": anon, "Authorization": f"Bearer {anon}"},
                json={"email": email, "password": _SMOKE_PASSWORD},
            )
            token_response.raise_for_status()
            try:
                token_payload: object = token_response.json()
                token_map = as_json_object(token_payload, source="auth password grant")
            except (ValueError, TypeError):
                return None
            token_raw = token_map.get("access_token")
            if isinstance(token_raw, str) and token_raw:
                return token_raw
    except (httpx.HTTPError, psycopg.Error, ValueError):
        return None
    return None


def default_http_smoke(repo_root: Path) -> tuple[bool, str]:
    """Authenticate and run read/chat/upload against the live API.

    Args:
        repo_root: Repository root.

    Returns:
        ``(ok, secret-free reason)``.
    """

    token = issue_smoke_access_token(repo_root)
    if token is None:
        return False, "local Auth bootstrap for old-API smoke failed"
    with httpx.Client(timeout=15.0) as client:
        ok, reason, _steps = execute_authenticated_smoke(
            api_base=api_base_url(),
            access_token=token,
            client=client,
        )
    return ok, reason


def default_hooks(repo_root: Path) -> OldApiSlotHooks:
    """Build Docker/HTTP hooks for a live Packet 2/7 run.

    Args:
        repo_root: Repository root.

    Returns:
        Hooks that inspect, recreate ``api``, and smoke HTTP.
    """

    return OldApiSlotHooks(
        inspect_image_id=docker_inspect_image_id,
        recreate_api=lambda image_id: recreate_api_with_image(repo_root, image_id),
        http_smoke=lambda: default_http_smoke(repo_root),
    )


def outcome_payload(outcome: OldApiSmokeOutcome) -> dict[str, object]:
    """Serialize one smoke outcome without secrets.

    Args:
        outcome: Classification result.

    Returns:
        JSON-object mapping.
    """

    return {
        "schema_version": OLD_API_SMOKE_SCHEMA_VERSION,
        "classification": outcome.classification,
        "reason": outcome.reason,
        "next_action": outcome.next_action,
        "freeze_api_id": outcome.freeze_api_id,
        "requested": outcome.requested,
        "resolved_image_id": outcome.resolved_image_id,
        "smoke_ran": outcome.smoke_ran,
        "restored_freeze": outcome.restored_freeze,
        "image_rebuilt": False,
        "holdout_opened": False,
        "steps": [
            {
                "name": step.name,
                "status_code": step.status_code,
                "ok": step.ok,
            }
            for step in outcome.steps
        ],
    }


def write_smoke_artifact(repo_root: Path, outcome: OldApiSmokeOutcome) -> Path:
    """Write the Packet 2/7 old-API smoke artifact.

    Args:
        repo_root: Repository root.
        outcome: Classification result.

    Returns:
        Artifact path.

    Side Effects:
        Overwrites ``docs/deployment/phase-09/candidate-old-api-new-schema-smoke.json``.
    """

    path = repo_root / ARTIFACT_DIR / OLD_API_SMOKE_ARTIFACT
    dump_canonical_json(outcome_payload(outcome), path)
    return path


def apply_outcome_to_handoff_row(
    row: dict[str, object], outcome: OldApiSmokeOutcome
) -> dict[str, object]:
    """Overlay smoke classification onto one Packet 2/7 handoff row.

    Args:
        row: Existing handoff object.
        outcome: Smoke result.

    Returns:
        Copied row with classification, reason, and next_action replaced.
    """

    updated = dict(row)
    updated["classification"] = outcome.classification
    updated["reason"] = outcome.reason
    updated["next_action"] = outcome.next_action
    return updated


def _blocked(
    *,
    freeze_api_id: str,
    reason: str,
    next_action: str,
    requested: str | None,
    resolved_image_id: str | None = None,
) -> OldApiSmokeOutcome:
    """Build a Blocked outcome.

    Args:
        freeze_api_id: Packet 1 API image Id.
        reason: Secret-free explanation.
        next_action: Packet 7 follow-up.
        requested: Env value, or ``None``.
        resolved_image_id: Inspected Id when known.

    Returns:
        Blocked classification with ``smoke_ran`` false.
    """

    return OldApiSmokeOutcome(
        classification="Blocked",
        reason=reason,
        next_action=next_action,
        freeze_api_id=freeze_api_id,
        requested=requested,
        resolved_image_id=resolved_image_id,
        smoke_ran=False,
        restored_freeze=False,
    )


def _failed(
    *,
    freeze_api_id: str,
    reason: str,
    next_action: str,
    requested: str | None,
    resolved_image_id: str | None = None,
    smoke_ran: bool = False,
    restored_freeze: bool = False,
    steps: tuple[SmokeStep, ...] = (),
) -> OldApiSmokeOutcome:
    """Build a Failed outcome.

    Args:
        freeze_api_id: Packet 1 API image Id.
        reason: Secret-free explanation.
        next_action: Packet 7 follow-up.
        requested: Env value, or ``None``.
        resolved_image_id: Inspected Id when known.
        smoke_ran: True when HTTP probes executed.
        restored_freeze: True when the freeze API slot was restored.
        steps: HTTP step summaries.

    Returns:
        Failed classification.
    """

    return OldApiSmokeOutcome(
        classification="Failed",
        reason=reason,
        next_action=next_action,
        freeze_api_id=freeze_api_id,
        requested=requested,
        resolved_image_id=resolved_image_id,
        smoke_ran=smoke_ran,
        restored_freeze=restored_freeze,
        steps=steps,
    )


def evaluate_old_api_new_schema_smoke(
    repo_root: Path,
    *,
    freeze_api_id: str,
    hooks: OldApiSlotHooks | None = None,
    run_live: bool = True,
    write_artifact: bool = True,
) -> OldApiSmokeOutcome:
    """Classify and optionally run old-API/new-schema authenticated smoke.

    Missing or blank ``SMART_RAG_OLD_API_IMAGE`` is Blocked, not Passed
    and not a pytest skip. A value that resolves to ``freeze_api_id`` is
    Failed. A live run recreates only ``api``, smokes, then restores the
    freeze Id.

    Args:
        repo_root: Repository root.
        freeze_api_id: Packet 1 API image Id that must not be smoked.
        hooks: Optional Docker/HTTP doubles. ``None`` uses Compose.
        run_live: When false, a resolved prior image stays Blocked.
        write_artifact: When true, write the JSON artifact.

    Returns:
        Fail-closed outcome.

    Side Effects:
        May recreate the Compose ``api`` service and write the smoke
        artifact. Does not open holdout, rebuild images, or provision AWS.
    """

    freeze = normalize_image_id(freeze_api_id)
    requested = read_old_api_image_env()
    if requested is None:
        outcome = _blocked(
            freeze_api_id=freeze,
            reason=MISSING_ENV_REASON,
            next_action=MISSING_ENV_NEXT,
            requested=None,
        )
        if write_artifact:
            write_smoke_artifact(repo_root, outcome)
        return outcome

    if ids_equal(requested, freeze):
        outcome = _failed(
            freeze_api_id=freeze,
            reason=FREEZE_REASON,
            next_action=FREEZE_NEXT,
            requested=requested,
            resolved_image_id=freeze,
        )
        if write_artifact:
            write_smoke_artifact(repo_root, outcome)
        return outcome

    slot = hooks or default_hooks(repo_root)
    inspected = slot.inspect_image_id(requested)
    if inspected is None:
        outcome = _blocked(
            freeze_api_id=freeze,
            reason=MISSING_IMAGE_REASON,
            next_action=MISSING_IMAGE_NEXT,
            requested=requested,
        )
        if write_artifact:
            write_smoke_artifact(repo_root, outcome)
        return outcome
    if ids_equal(inspected, freeze):
        outcome = _failed(
            freeze_api_id=freeze,
            reason=FREEZE_REASON,
            next_action=FREEZE_NEXT,
            requested=requested,
            resolved_image_id=inspected,
        )
        if write_artifact:
            write_smoke_artifact(repo_root, outcome)
        return outcome

    if not run_live:
        outcome = _blocked(
            freeze_api_id=freeze,
            reason=(
                "Prior API image resolved; live authenticated smoke was "
                "not executed in this run."
            ),
            next_action=MISSING_IMAGE_NEXT,
            requested=requested,
            resolved_image_id=inspected,
        )
        if write_artifact:
            write_smoke_artifact(repo_root, outcome)
        return outcome

    outcome = _failed(
        freeze_api_id=freeze,
        reason="prior API drain smoke did not complete",
        next_action=MISSING_IMAGE_NEXT,
        requested=requested,
        resolved_image_id=inspected,
    )
    try:
        running = slot.recreate_api(inspected)
        if running is None or not ids_equal(running, inspected):
            outcome = _failed(
                freeze_api_id=freeze,
                reason=("Prior API container did not start on the requested image Id."),
                next_action=MISSING_IMAGE_NEXT,
                requested=requested,
                resolved_image_id=inspected,
            )
        elif ids_equal(running, freeze):
            outcome = _failed(
                freeze_api_id=freeze,
                reason=FREEZE_REASON,
                next_action=FREEZE_NEXT,
                requested=requested,
                resolved_image_id=inspected,
            )
        else:
            ok, detail = slot.http_smoke()
            if ok:
                outcome = OldApiSmokeOutcome(
                    classification="Passed",
                    reason=(
                        "Prior API image served authenticated "
                        "read/chat/upload against the current schema."
                    ),
                    next_action=("Keep the prior digest for the next expand window."),
                    freeze_api_id=freeze,
                    requested=requested,
                    resolved_image_id=inspected,
                    smoke_ran=True,
                    restored_freeze=False,
                )
            else:
                outcome = _failed(
                    freeze_api_id=freeze,
                    reason=detail,
                    next_action=(
                        "Repair old-API compatibility on the current "
                        "schema, then re-run the smoke."
                    ),
                    requested=requested,
                    resolved_image_id=inspected,
                    smoke_ran=True,
                )
    except (CandidateReleaseError, OSError, httpx.HTTPError) as exc:
        outcome = _failed(
            freeze_api_id=freeze,
            reason=f"prior API drain smoke failed ({type(exc).__name__})",
            next_action=MISSING_IMAGE_NEXT,
            requested=requested,
            resolved_image_id=inspected,
        )
    restored_id: str | None
    try:
        restored_id = slot.recreate_api(freeze)
    except (CandidateReleaseError, OSError):
        restored_id = None
    restored = restored_id is not None and ids_equal(restored_id, freeze)
    if not restored:
        outcome = _failed(
            freeze_api_id=freeze,
            reason=(
                f"{outcome.reason} Freeze API slot was not restored "
                "after the drain smoke."
            ),
            next_action=(
                "Recreate api from the Packet 1 freeze Id before further "
                "Packet 2/7 work."
            ),
            requested=requested,
            resolved_image_id=inspected,
            smoke_ran=outcome.smoke_ran,
            restored_freeze=False,
        )
    else:
        outcome = OldApiSmokeOutcome(
            classification=outcome.classification,
            reason=outcome.reason,
            next_action=outcome.next_action,
            freeze_api_id=outcome.freeze_api_id,
            requested=outcome.requested,
            resolved_image_id=outcome.resolved_image_id,
            smoke_ran=outcome.smoke_ran,
            restored_freeze=True,
            steps=outcome.steps,
        )
    if write_artifact:
        write_smoke_artifact(repo_root, outcome)
    return outcome
