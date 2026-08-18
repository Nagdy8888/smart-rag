"""Compact image-scan summaries. Full dumps stay gitignored."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from smart_rag_core.release.constants import SCAN_SCHEMA_VERSION


class ImageScanSummary(BaseModel):
    """Severity counts for one scanned candidate image.

    Attributes:
        image_name: Scanned image reference.
        status: ``passed``, ``failed``, ``blocked``, or ``not_run``.
        critical: Critical finding count.
        high: High finding count.
        medium: Medium finding count.
        low: Low finding count.
        unknown: Unknown finding count.
        tool: Scanner name.
        detail: Bounded reason when blocked or not run.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    image_name: str = Field(min_length=1, max_length=256)
    status: Literal["passed", "failed", "blocked", "not_run"]
    critical: int = Field(ge=0)
    high: int = Field(ge=0, default=0)
    medium: int = Field(ge=0, default=0)
    low: int = Field(ge=0, default=0)
    unknown: int = Field(ge=0, default=0)
    tool: str = Field(min_length=1, max_length=64)
    detail: str = ""


class CandidateScanSummary(BaseModel):
    """Packet 1 scan roll-up. Packet 6 re-runs full SBOM/Trivy.

    Attributes:
        schema_version: Frozen scan schema.
        images: Per-image summaries.
        pip_audit_status: Host Python audit classification.
        pnpm_audit_status: Host Node audit classification.
        gitleaks_status: Secret scan classification.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["phase09-candidate-scan-v1"] = SCAN_SCHEMA_VERSION
    images: tuple[ImageScanSummary, ...]
    pip_audit_status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"
    pnpm_audit_status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"
    gitleaks_status: Literal["passed", "failed", "blocked", "not_run"] = "not_run"


def summarize_trivy_report(
    payload: Mapping[str, object],
    *,
    image_name: str,
) -> ImageScanSummary:
    """Count severities from a Trivy JSON report.

    Args:
        payload: Trivy ``--format json`` object.
        image_name: Image that was scanned.

    Returns:
        Compact summary. ``failed`` when Critical findings are present.
    """

    counts = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0, "UNKNOWN": 0}
    results = payload.get("Results")
    if isinstance(results, list):
        for result in cast(list[object], results):
            if not isinstance(result, dict):
                continue
            typed_result = cast(dict[str, object], result)
            vulns = typed_result.get("Vulnerabilities")
            if not isinstance(vulns, Sequence):
                continue
            for vuln in cast(Sequence[object], vulns):
                if not isinstance(vuln, dict):
                    continue
                typed_vuln = cast(dict[str, object], vuln)
                severity = str(typed_vuln.get("Severity", "UNKNOWN")).upper()
                if severity in counts:
                    counts[severity] += 1
                else:
                    counts["UNKNOWN"] += 1
    critical = counts["CRITICAL"]
    status: Literal["passed", "failed", "blocked", "not_run"] = (
        "failed" if critical else "passed"
    )
    return ImageScanSummary(
        image_name=image_name,
        status=status,
        critical=critical,
        high=counts["HIGH"],
        medium=counts["MEDIUM"],
        low=counts["LOW"],
        unknown=counts["UNKNOWN"],
        tool="trivy",
        detail="unresolved Critical findings" if critical else "",
    )


def trivy_critical_ids(
    payload: Mapping[str, object],
    *,
    limit: int = 30,
) -> tuple[str, ...]:
    """Return unique Critical vulnerability IDs from a Trivy report.

    Args:
        payload: Trivy ``--format json`` object.
        limit: Maximum IDs retained.

    Returns:
        Sorted VulnerabilityID values. Does not include package payloads.
    """

    found: set[str] = set()
    results = payload.get("Results")
    if isinstance(results, list):
        for result in cast(list[object], results):
            if not isinstance(result, dict):
                continue
            typed_result = cast(dict[str, object], result)
            vulns = typed_result.get("Vulnerabilities")
            if not isinstance(vulns, Sequence):
                continue
            for vuln in cast(Sequence[object], vulns):
                if not isinstance(vuln, dict):
                    continue
                typed_vuln = cast(dict[str, object], vuln)
                if str(typed_vuln.get("Severity", "")).upper() != "CRITICAL":
                    continue
                vuln_id = typed_vuln.get("VulnerabilityID")
                if isinstance(vuln_id, str) and vuln_id:
                    found.add(vuln_id)
    return tuple(sorted(found)[:limit])


def blocked_scan(image_name: str, *, tool: str, detail: str) -> ImageScanSummary:
    """Return an honest Blocked/Not Run row.

    Args:
        image_name: Image that was not scanned.
        tool: Scanner that could not run.
        detail: Bounded reason.

    Returns:
        Summary with ``blocked`` status and zero counts.
    """

    return ImageScanSummary(
        image_name=image_name,
        status="blocked",
        critical=0,
        tool=tool,
        detail=detail[:500],
    )
