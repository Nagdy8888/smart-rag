"""Replay, resume, leakage, and legacy-status contracts for progress fixtures."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from smart_rag_core.query_admission.repository.records import QueryRunRecord
from smart_rag_core.security.identity import CallerContext, UserRole
from smart_rag_core.sse.catalog import TERMINAL_SSE_EVENT_TYPES, StatusPayload
from smart_rag_core.sse.framing import ParsedSseEvent, iter_known_sse_events
from smart_rag_core.sse.sanitize import validate_sse_payload
from smart_rag_core.sse.store import MemoryRunEventStore

FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "frontend"
    / "tests"
    / "fixtures"
    / "sse"
)
META = json.loads((FIXTURE_DIR / "route-progress.json").read_text(encoding="utf-8"))


def _caller() -> CallerContext:
    """Return a stable member caller.

    Returns:
        Frozen caller context.
    """

    return CallerContext(
        user_id="00000000-0000-4000-8000-000000000011",
        role=UserRole.MEMBER,
        authorization_version=1,
    )


def _load_events(name: str) -> list[ParsedSseEvent]:
    """Parse one checked-in SSE fixture.

    Args:
        name: Fixture filename.

    Returns:
        Known catalog events.
    """

    raw = (FIXTURE_DIR / name).read_text(encoding="utf-8")
    return list(iter_known_sse_events(raw))


def test_fixtures_are_monotonic_with_one_terminal_and_no_leaks() -> None:
    """Every public fixture stays catalog-safe and singly terminated."""

    forbidden = tuple(META["forbidden_substrings"])
    for name in (
        "general-progress.sse",
        "company-progress.sse",
        "invalid-progress.sse",
        "reconnect-progress.sse",
        "verified-long-answer.sse",
        "cancel-progress.sse",
    ):
        raw = (FIXTURE_DIR / name).read_text(encoding="utf-8")
        events = list(iter_known_sse_events(raw))
        sequences = [item.sequence for item in events if item.sequence is not None]
        assert sequences == list(range(1, len(sequences) + 1)), name
        terminals = [
            item.event_type
            for item in events
            if item.event_type in TERMINAL_SSE_EVENT_TYPES
        ]
        assert len(terminals) == 1, name
        for item in events:
            validate_sse_payload(item.event_type, item.payload)
        for marker in forbidden:
            assert marker not in raw
        assert META["leakage_marker"] not in raw


def test_route_fixtures_match_required_and_forbidden_stages() -> None:
    """Checked-in route files encode topology, not a hard-coded company pipeline."""

    for _route, spec in META["routes"].items():
        events = _load_events(spec["file"])
        stages = {
            str(item.payload.get("stage"))
            for item in events
            if item.event_type == "status" and item.payload.get("stage")
        }
        assert set(spec["required_stages"]) <= stages
        assert set(spec["forbidden_stages"]).isdisjoint(stages)
        tools = [
            item.payload.get("tool_key")
            for item in events
            if item.event_type == "tool_progress"
        ]
        assert tools == spec["tool_keys"]
        types = [item.event_type for item in events]
        if "token_delta" in types:
            verify = next(
                index
                for index, item in enumerate(events)
                if item.event_type == "status"
                and item.payload.get("stage") == "verify_answer"
                and item.payload.get("phase") == "completed"
            )
            assert types.index("token_delta") > verify


def test_resume_after_n_returns_only_later_events() -> None:
    """Reconnect after sequence N replays a strict suffix."""

    events = _load_events("reconnect-progress.sse")
    after = 4
    later = [item for item in events if (item.sequence or 0) > after]
    assert later
    assert all((item.sequence or 0) > after for item in later)
    assert later[0].sequence == after + 1


def test_legacy_status_without_phase_replays() -> None:
    """Persisted status rows that omit ``phase`` remain legal."""

    events = _load_events("reconnect-progress.sse")
    legacy = [
        item
        for item in events
        if item.event_type == "status" and "phase" not in item.payload
    ]
    assert legacy
    for item in legacy:
        payload = StatusPayload.model_validate(item.payload)
        assert payload.phase is None
        validate_sse_payload("status", item.payload)


def test_memory_store_replay_and_cancel_do_not_fabricate_completed() -> None:
    """Persisted cancel remains the only terminal after resume."""

    store = MemoryRunEventStore()
    caller = _caller()
    run_id = uuid4()
    store.register_run(
        caller=caller,
        record=QueryRunRecord(
            run_id=run_id,
            conversation_id=uuid4(),
            creator_user_id=UUID(str(caller.user_id)),
            status="running",
            reservation_id=uuid4(),
            created_at=datetime.now(UTC),
        ),
    )
    for item in _load_events("cancel-progress.sse"):
        store.append(
            caller,
            run_id=run_id,
            event_type=item.event_type,
            payload=dict(item.payload),
        )
    replayed = store.list_after(caller, run_id=run_id, after=1)
    types = [item.event_type for item in replayed]
    assert "cancelled" in types
    assert "completed" not in types
    assert types.count("cancelled") == 1
    suffix = store.list_after(caller, run_id=run_id, after=2)
    assert [item.event_type for item in suffix] == ["cancelled"]
