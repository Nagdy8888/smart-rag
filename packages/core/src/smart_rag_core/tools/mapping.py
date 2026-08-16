"""Deterministic profile-to-tool mapping for known optional intents."""

from __future__ import annotations

from smart_rag_core.tools.constants import DEFAULT_AMBIGUOUS_EXPORT_KEY
from smart_rag_core.tools.exceptions import ToolError
from smart_rag_core.tools.models import OptionalIntent

_EXPLICIT: dict[OptionalIntent, str] = {
    OptionalIntent.EXPORT_CSV: "export_csv",
    OptionalIntent.EXPORT_XLSX: "export_xlsx",
    OptionalIntent.AMBIGUOUS_EXPORT: DEFAULT_AMBIGUOUS_EXPORT_KEY,
}


def map_optional_intent(intent: OptionalIntent) -> str | None:
    """Return the allow-listed tool key for a known optional intent.

    Administration stays discovery-or-reject: v1 runtime uses the
    comparative-fixture policy and does not auto-select admin tools.
    ``NONE`` returns None so the core path never loads a manifest.

    Args:
        intent: Typed optional intent.

    Returns:
        Tool key, or None when no optional tool should run.

    Raises:
        ToolError: If a core retrieve key would be selected.
    """

    from smart_rag_core.tools.constants import CORE_FORBIDDEN_TOOL_KEYS

    if intent is OptionalIntent.NONE or intent is OptionalIntent.ADMINISTRATION:
        return None
    key = _EXPLICIT[intent]
    if key in CORE_FORBIDDEN_TOOL_KEYS:
        raise ToolError("core_tool_not_catalogable")
    return key
