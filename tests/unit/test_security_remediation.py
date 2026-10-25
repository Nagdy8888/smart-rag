"""Offline regressions for the source-audit security boundaries."""

from __future__ import annotations

import asyncio
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import fitz
import httpx
import pytest
import yaml
from smart_rag_api.services.sse.service import SseStreamService
from smart_rag_core.ingestion.crawl.adapter import BoundedCrawlAdapter
from smart_rag_core.ingestion.crawl.policy import (
    ApprovedCrawlScope,
    CrawlPolicyError,
    normalize_url,
)
from smart_rag_core.ingestion.figures import materialize as figure_module
from smart_rag_core.ingestion.figures.describe import figure_describer
from smart_rag_core.ingestion.parser.types import PdfLocator
from smart_rag_core.query_admission.exceptions import QueryAdmissionError
from smart_rag_core.security.external_processing import (
    CategoryDisposition,
    ContentClass,
    DetectorResult,
    ExternalProcessingDecisionInput,
)
from smart_rag_core.security.jwks import JwksVerificationError, JwksVerifier
from smart_rag_core.security.profile_snapshot import is_session_revoked

from tests.support.query_sse import caller as make_caller
from tests.unit import test_phase10_packet4 as jwk_fixtures
from tests.unit.typed_attrs import typed_attr

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    "target",
    [
        "https://other.example/page",
        "https://approved.example.evil.com/",
        "https://evilapproved.example/",
        "https://unrelated.org/",
    ],
)
def test_redirect_denied_before_dns_or_proxy(target: str) -> None:
    """A public off-domain redirect must not reach even the second DNS lookup."""
    proxy = MagicMock()
    proxy.fetch.return_value = SimpleNamespace(
        peer_ip="8.8.8.8", status_code=302, headers={"Location": target}
    )
    adapter = BoundedCrawlAdapter(proxy=proxy)
    scope = ApprovedCrawlScope(
        approval_id="approval",
        source_id="source",
        start_url="https://approved.example/",
        approved_domain="approved.example",
        policy_version="test",
        max_depth=1,
        max_pages=2,
        requester_user_id=None,
        reviewer_user_id=None,
    )
    with patch.object(
        adapter,
        "_resolve",
        return_value=SimpleNamespace(
            hostname="approved.example", pinned_ips=("8.8.8.8",)
        ),
    ) as resolver:
        with pytest.raises(CrawlPolicyError):
            typed_attr(adapter, "_fetch_page")(
                normalize_url(scope.start_url), redirect_hop=0, scope=scope
            )
    assert proxy.fetch.call_count == 1
    assert resolver.call_count == 1


def test_jwks_random_kid_burst_and_rollover(monkeypatch: pytest.MonkeyPatch) -> None:
    """Distinct misses share one cooldown; genuine rollover works after it."""
    from cryptography.hazmat.primitives.asymmetric import ec

    clock = [100.0]
    monkeypatch.setattr("smart_rag_core.security.jwks.time.monotonic", lambda: clock[0])
    old = ec.generate_private_key(ec.SECP256R1())
    new = ec.generate_private_key(ec.SECP256R1())
    keys = [typed_attr(jwk_fixtures, "_public_jwk")(old, "old")]
    calls: list[str] = []

    def fetch(_client: httpx.Client, url: Any) -> httpx.Response:
        """Serve only the synthetic current key set and count refreshes."""
        calls.append(str(url))
        return httpx.Response(
            200, json={"keys": list(keys)}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.Client, "get", fetch)
    verifier = JwksVerifier(supabase_url="http://127.0.0.1:54321")
    verifier.verify_access_token(
        typed_attr(jwk_fixtures, "_sign_es256")(old, kid="old")
    )

    def miss(index: int) -> None:
        """Submit a unique invalid key without contacting a real identity service."""
        with pytest.raises(JwksVerificationError):
            verifier.verify_access_token(
                typed_attr(jwk_fixtures, "_sign_es256")(new, kid=f"random-{index}")
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(miss, range(32)))
    assert len(calls) == 1
    keys.append(typed_attr(jwk_fixtures, "_public_jwk")(new, "new"))
    clock[0] += 10.1
    assert (
        verifier.verify_access_token(
            typed_attr(jwk_fixtures, "_sign_es256")(new, kid="new")
        ).key_id
        == "new"
    )
    assert len(calls) == 2


def test_jwks_failed_fetch_is_also_throttled(monkeypatch: pytest.MonkeyPatch) -> None:
    """An Auth outage cannot turn each invalid token into a fresh outbound fetch."""
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    token = typed_attr(jwk_fixtures, "_sign_es256")(key, kid="unknown")
    with patch.object(
        httpx.Client, "get", side_effect=httpx.ConnectError("offline")
    ) as get:
        verifier = JwksVerifier(supabase_url="http://127.0.0.1:54321")
        for _ in range(10):
            with pytest.raises(JwksVerificationError):
                verifier.verify_access_token(token)
        assert get.call_count == 1


def test_trusted_key_does_not_wait_for_an_attacker_refresh() -> None:
    """Known valid identities do not acquire the slow miss-refresh lock."""
    from cryptography.hazmat.primitives.asymmetric import ec

    key = ec.generate_private_key(ec.SECP256R1())
    token = typed_attr(jwk_fixtures, "_sign_es256")(key, kid="known")
    jwk = typed_attr(jwk_fixtures, "_public_jwk")(key, "known")
    with patch.object(
        httpx.Client,
        "get",
        return_value=httpx.Response(
            200,
            json={"keys": [jwk]},
            request=httpx.Request("GET", "https://dummy.example"),
        ),
    ):
        verifier = JwksVerifier(supabase_url="http://127.0.0.1:54321")
        verifier.verify_access_token(token)
        refresh_lock: threading.Lock = typed_attr(verifier, "_refresh_lock")
        with ThreadPoolExecutor(max_workers=1) as pool:
            with refresh_lock:
                future = pool.submit(verifier.verify_access_token, token)
                assert future.result(timeout=1).key_id == "known"


def test_revocation_without_iat_fails_closed_without_database() -> None:
    """A token with unknown age cannot evade profile-wide revocation."""
    with patch("smart_rag_core.security.profile_snapshot.psycopg.connect") as db:
        assert is_session_revoked(
            "unused",
            session_id=None,
            issued_at=None,
            session_revoked_at=datetime.now(UTC),
        )
        db.assert_not_called()


@pytest.mark.parametrize(
    "box",
    [
        (0, 0, float("inf"), 10),
        (0, 0, float("nan"), 10),
        (0, 0, 1e9, 1e9),
        (10, 0, 0, 10),
        (0, 10, 10, 0),
        (0, 0, 0, 10),
        (-1e9, -1e9, 1e9, 1e9),
    ],
)
def test_figure_geometry_rejected_before_allocation(box: tuple[float, ...]) -> None:
    """Invalid/oversized crops cannot reach get_pixmap or extract_image."""
    page = MagicMock()
    page.rect = fitz.Rect(-1e9, -1e9, 1e9, 1e9)
    document = MagicMock(page_count=1)
    document.load_page.return_value = page
    element = SimpleNamespace(
        locator=PdfLocator(
            page_index=0, bbox_x0=box[0], bbox_y0=box[1], bbox_x1=box[2], bbox_y1=box[3]
        ),
        metadata={"xref": 1},
    )
    assert typed_attr(figure_module, "_crop")(document, element) == b""
    page.get_pixmap.assert_not_called()
    document.extract_image.assert_not_called()


def governance(**changes: Any) -> ExternalProcessingDecisionInput:
    """Return approved real-content policy, with one explicit changed condition."""
    return ExternalProcessingDecisionInput.model_validate(
        {
            "attestation_present": True,
            "category": CategoryDisposition.ALLOWED,
            "detector_results": [DetectorResult.CLEAN],
            "scan_evidence_current": True,
            "provider_settings_verified": True,
            "policy_version_matches": True,
            "content_class": ContentClass.REAL_COMPANY,
        }
        | changes
    )


@pytest.mark.parametrize(
    "denial",
    [
        {"attestation_present": False},
        {"attestation_expired": True},
        {"attestation_contradictory": True},
        {"category": CategoryDisposition.PROHIBITED},
        {"category": CategoryDisposition.UNKNOWN},
        {"category": CategoryDisposition.MANDATORY_REVIEW},
        {"detector_results": [DetectorResult.POSITIVE]},
        {"detector_results": [DetectorResult.UNKNOWN]},
        {"scan_evidence_current": False},
        {"provider_settings_verified": False},
        {"policy_version_matches": False},
    ],
)
def test_figure_denial_never_opens_db_or_provider(denial: dict[str, Any]) -> None:
    """All governance denials occur before credentials, reservations or sends."""
    with (
        patch("smart_rag_core.ingestion.figures.describe.psycopg.connect") as db,
        patch(
            "smart_rag_core.ingestion.figures.describe.execute_figure_description"
        ) as send,
    ):
        describe = figure_describer(
            mock_model_mode=False,
            governance=governance(**denial),
            postgres_url="unused",
            job_id=uuid4(),
            lease_token=str(uuid4()),
            operation_key="test",
        )
        assert describe(b"dummy-png") == ""
        db.assert_not_called()
        send.assert_not_called()


@pytest.mark.parametrize("uncertain", [False, True])
def test_figure_attempt_is_durable_before_send_and_replay_never_resends(
    uncertain: bool,
) -> None:
    """A sent/uncertain operation is never retried; measured usage is retained."""
    rows: dict[str, dict[str, Any]] = {}
    connection = MagicMock()
    ledger = MagicMock()

    def fetch(**kw: Any) -> dict[str, Any] | None:
        """Look up the persistent fake operation ledger."""
        return rows.get(kw["operation_key"])

    ledger.fetch_result.side_effect = fetch

    def record(**kw: Any) -> None:
        """Persist one fake operation marker for the replay assertions."""
        rows[kw["operation_key"]] = kw["result_ref"]

    ledger.record_completed.side_effect = record

    def send(**kw: Any) -> str:
        """Assert admission preceded the send and simulate its provider outcome."""
        assert any(k.endswith(":attempt") for k in rows)
        assert connection.commit.call_count == 1
        if uncertain:
            raise TimeoutError("dummy uncertain send")
        kw["usage_observer"](100, 20, "dummy-request")
        return "A plotted line."

    prefix = "smart_rag_core.ingestion.figures.describe."
    with (
        patch(prefix + "psycopg.connect") as connect,
        patch(prefix + "JobOperationLedger", return_value=ledger),
        patch(prefix + "JobAdmissionService") as admission,
        patch(prefix + "SharedSettings") as settings,
        patch(prefix + "execute_figure_description", side_effect=send) as provider,
    ):
        connect.return_value.__enter__.return_value = connection
        settings.return_value.openai_api_key.get_secret_value.return_value = "dummy"
        describe = figure_describer(
            mock_model_mode=False,
            governance=governance(),
            postgres_url="unused",
            job_id=uuid4(),
            lease_token=str(uuid4()),
            operation_key="op",
        )
        if uncertain:
            with pytest.raises(TimeoutError):
                describe(b"dummy-png")
            assert describe(b"dummy-png") == ""
            assert provider.call_count == 1
            return
        assert describe(b"dummy-png") == "A plotted line."
        assert describe(b"dummy-png") == "A plotted line."
        assert provider.call_count == 1
        admission.return_value.create_ingestion_budget_reservation.assert_called_once()
        result = next(v for k, v in rows.items() if k.endswith(":result"))
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 20
        rows.pop(next(k for k in rows if k.endswith(":result")))
        assert describe(b"dummy-png") == ""
        assert provider.call_count == 1


def test_figure_budget_denial_prevents_send() -> None:
    """Exhausted durable admission cannot create a send attempt."""
    prefix = "smart_rag_core.ingestion.figures.describe."
    ledger = MagicMock()
    ledger.fetch_result.return_value = None
    with (
        patch(prefix + "psycopg.connect"),
        patch(prefix + "JobOperationLedger", return_value=ledger),
        patch(prefix + "JobAdmissionService") as admission,
        patch(prefix + "SharedSettings") as settings,
        patch(prefix + "execute_figure_description") as provider,
    ):
        settings.return_value.openai_api_key.get_secret_value.return_value = "dummy"
        admission.return_value.create_ingestion_budget_reservation.side_effect = (
            RuntimeError("budget_exhausted")
        )
        describe = figure_describer(
            mock_model_mode=False,
            governance=governance(),
            postgres_url="unused",
            job_id=uuid4(),
            lease_token=str(uuid4()),
            operation_key="budget",
        )
        with pytest.raises(RuntimeError, match="budget_exhausted"):
            describe(b"dummy-png")
        provider.assert_not_called()
        ledger.record_completed.assert_not_called()


@pytest.mark.parametrize(
    "transition", ["expired", "revoked", "disabled", "role", "authz", "missing"]
)
def test_stream_stops_for_identity_transition(transition: str) -> None:
    """No frame replay follows a failed expiry/profile/session check."""
    caller = make_caller().model_copy(
        update={
            "token_expires_at": 1 if transition == "expired" else 4_000_000_000,
            "token_issued_at": 100,
            "session_id": "dummy",
        }
    )
    store = MagicMock()
    service = SseStreamService(
        store=store,
        registry=MagicMock(),
        executor=MagicMock(),
        sse_schema_version="1",
        postgres_url="unused",
    )
    snapshot = SimpleNamespace(
        disabled=transition == "disabled",
        role="viewer" if transition == "role" else caller.role,
        authorization_version=999
        if transition == "authz"
        else caller.authorization_version,
        session_revoked_at=None,
    )
    prefix = "smart_rag_api.services.sse.service."

    async def drain() -> None:
        """Reject delivery of any frame after an identity check fails."""
        async for _ in typed_attr(service, "_replay")(caller, uuid4(), 0):
            pytest.fail("unauthorized frame")

    with (
        patch(
            prefix + "load_profile_snapshot",
            return_value=None if transition == "missing" else snapshot,
        ),
        patch(prefix + "is_session_revoked", return_value=transition == "revoked"),
    ):
        with pytest.raises(QueryAdmissionError):
            asyncio.run(drain())
    store.list_after.assert_not_called()


@pytest.mark.parametrize(
    "name", ["staging-migrate", "production-migrate", "staging-deploy"]
)
def test_ssm_parameters_are_data_and_reject_shell_payloads(name: str) -> None:
    """Named documents forbid raw interpolation and constrain all input strings."""
    data = yaml.safe_load(
        (ROOT / "infra/ec2/ssm-documents" / (name + ".yml")).read_text()
    )
    script = "\n".join(data["mainSteps"][0]["inputs"]["runCommand"])
    assert "{{" not in script
    for key, parameter in data["parameters"].items():
        assert parameter["interpolationType"] == "ENV_VAR"
        assert "${SSM_" + key in script
        for attack in ["$(touch /tmp/owned)", "`id`", 'x";id;#', "a\nb", "a;b"]:
            assert re.fullmatch(parameter["allowedPattern"], attack) is None


def test_no_maintained_http_origin_can_forward_private_traffic() -> None:
    """Terraform and the compatibility Caddy path cannot select HTTP origins."""
    variables = (ROOT / "infra/ec2/variables.tf").read_text()
    assert 'var.origin_protocol_policy == "https-only"' in variables
    assert "http://:443" not in (ROOT / "infra/ec2/Caddyfile.http443").read_text()
    assert (
        "CADDYFILE_PATH=./Caddyfile.http443"
        not in (ROOT / "infra/ec2/.env.staging.example").read_text()
    )


def test_open_stream_rechecks_session_before_later_private_frame() -> None:
    """Revocation while the generator is suspended blocks the next frame."""
    caller = make_caller().model_copy(
        update={
            "token_expires_at": 4_000_000_000,
            "token_issued_at": 100,
            "session_id": "dummy",
        }
    )
    store = MagicMock()
    store.list_after.return_value = [
        SimpleNamespace(
            sequence=1, event_type="token_delta", payload={"text": "first"}
        ),
        SimpleNamespace(
            sequence=2, event_type="token_delta", payload={"text": "private-later"}
        ),
    ]
    service = SseStreamService(
        store=store,
        registry=MagicMock(),
        executor=MagicMock(),
        sse_schema_version="1",
        postgres_url="unused",
    )
    snapshot = SimpleNamespace(
        disabled=False,
        role=caller.role,
        authorization_version=caller.authorization_version,
        session_revoked_at=None,
    )
    clock = [100.0]
    revoked = [False]
    prefix = "smart_rag_api.services.sse.service."

    async def exercise() -> None:
        """Revoke a session between two attempts to advance the same stream."""
        stream = typed_attr(service, "_replay")(caller, uuid4(), 0)
        first = await anext(stream)
        assert "first" in first[0]
        revoked[0] = True
        clock[0] += 1.01
        with pytest.raises(QueryAdmissionError, match="session_revoked"):
            await anext(stream)

    def is_revoked(*_args: object, **_kwargs: object) -> bool:
        """Simulate session revocation between frames."""
        return revoked[0]

    with (
        patch(prefix + "load_profile_snapshot", return_value=snapshot),
        patch(prefix + "is_session_revoked", side_effect=is_revoked),
        patch(prefix + "time.monotonic", side_effect=lambda: clock[0]),
    ):
        asyncio.run(exercise())
