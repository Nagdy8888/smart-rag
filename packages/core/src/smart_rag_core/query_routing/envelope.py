"""Reserved packet 1 envelope versus planner-selected effective family."""

from __future__ import annotations

from smart_rag_core.query_admission.ceilings import envelope_for_family
from smart_rag_core.query_admission.context import AuthorizedRuntimeContext
from smart_rag_core.query_profile.phase6_map import Phase6RouteFamily
from smart_rag_core.query_routing.constants import FALLBACK_ENVELOPE_CANNOT_ENLARGE
from smart_rag_core.query_routing.exceptions import QueryRoutingError


def family_fits_reservation(
    effective: Phase6RouteFamily,
    reserved: Phase6RouteFamily,
) -> bool:
    """Return whether ``effective`` can run inside the reserved envelope.

    The planner never enlarges packet 1 remaining ceilings. A client Combined
    request cannot expand a Hybrid reservation.

    Args:
        effective: Family the matrix selected.
        reserved: Family reserved at admit.

    Returns:
        True when deadline, model-call, tool, and USD envelopes fit.
    """

    needed = envelope_for_family(effective)
    held = envelope_for_family(reserved)
    return (
        needed.deadline_seconds <= held.deadline_seconds
        and needed.model_call_ceiling <= held.model_call_ceiling
        and needed.tool_ceiling <= held.tool_ceiling
        and needed.envelope_usd <= held.envelope_usd
    )


def clamp_family_to_reservation(
    desired: Phase6RouteFamily,
    runtime: AuthorizedRuntimeContext,
) -> tuple[Phase6RouteFamily, str | None]:
    """Clamp a desired family so it never exceeds the reserved envelope.

    Args:
        desired: Matrix-selected family.
        runtime: Packet 1 authorized context. ``route_family`` is the envelope.

    Returns:
        Effective family and optional ``envelope_cannot_enlarge`` reason.
    """

    reserved = runtime.route_family
    if family_fits_reservation(desired, reserved):
        remaining_ok = (
            envelope_for_family(desired).model_call_ceiling
            <= runtime.model_call_ceiling
            and envelope_for_family(desired).tool_ceiling <= runtime.tool_ceiling
        )
        if remaining_ok:
            return desired, None
    if desired is reserved:
        return desired, None
    if not family_fits_reservation(Phase6RouteFamily.HYBRID, reserved):
        return reserved, FALLBACK_ENVELOPE_CANNOT_ENLARGE
    return Phase6RouteFamily.HYBRID, FALLBACK_ENVELOPE_CANNOT_ENLARGE


def reject_production_manual_override(
    *,
    surface: str,
    requested_manual_route: str | None,
) -> None:
    """Reject production manual routing. Diagnostic surfaces may record it.

    Args:
        surface: ``production`` or ``diagnostic``.
        requested_manual_route: Client-supplied family, if any.

    Raises:
        QueryRoutingError: ``production_manual_override`` on production.
    """

    if requested_manual_route and surface == "production":
        raise QueryRoutingError("production_manual_override")
