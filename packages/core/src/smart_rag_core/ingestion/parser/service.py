"""Parser orchestration service with governance integration."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from smart_rag_core.ingestion.governance import (
    ExtractionGovernanceInput,
    evaluate_extraction_governance,
)
from smart_rag_core.ingestion.detectors import DetectorFamilyOutcome
from smart_rag_core.ingestion.parser.sandbox.launcher import (
    ParserSandboxLauncher,
    SandboxLaunchConfig,
    inprocess_parser_permitted,
)
from smart_rag_core.ingestion.parser.types import ParseDisposition, ParseResult


@dataclass(frozen=True, slots=True)
class ParserInvocation:
    """One bounded parser invocation request."""

    payload: bytes
    content_hash: str
    filename: str
    media_type: str | None = None
    format_key: str | None = None


@dataclass(frozen=True, slots=True)
class ParserServiceResult:
    """Parse output plus governance decision."""

    parse_result: ParseResult
    promotion_allowed: bool
    external_processing_allowed: bool
    governance_detail: str
    detector_outcomes: tuple[DetectorFamilyOutcome, ...] = ()


class ParserService:
    """Coordinate sandbox parsing and post-extraction governance."""

    def __init__(self, launcher: ParserSandboxLauncher | None = None) -> None:
        """Initialize with optional sandbox launcher override.

        Args:
            launcher: Explicit launcher. ``None`` uses Docker by default.
                In-process parsing is selected only when
                ``ALLOW_INPROCESS_PARSER`` is set and ``APP_ENV=test``.
        """

        if launcher is not None:
            self._launcher = launcher
        elif inprocess_parser_permitted():
            self._launcher = ParserSandboxLauncher(
                config=SandboxLaunchConfig(
                    image="smart-rag-parser-sandbox:local",
                    use_docker=False,
                )
            )
        else:
            self._launcher = ParserSandboxLauncher()

    def parse_and_govern(
        self,
        invocation: ParserInvocation,
        *,
        governance: ExtractionGovernanceInput,
        scan_evidence_current: bool,
    ) -> ParserServiceResult:
        """Parse one object and run extracted-text governance fail-closed.

        Args:
            invocation: Object bytes and metadata.
            governance: Uploader attestation and review metadata.
            scan_evidence_current: Whether scan evidence is current.

        Returns:
            Parse and governance outcome. Failed parses never allow promotion.
        """

        expected = hashlib.sha256(invocation.payload).hexdigest()
        if expected != invocation.content_hash:
            failed = _hash_mismatch_result(
                invocation.content_hash, invocation.format_key
            )
            return ParserServiceResult(
                parse_result=failed,
                promotion_allowed=False,
                external_processing_allowed=False,
                governance_detail="content hash mismatch",
            )
        parse_result = self._launcher.run(
            payload=invocation.payload,
            content_hash=invocation.content_hash,
            filename=invocation.filename,
            media_type=invocation.media_type,
            format_key=invocation.format_key,
        )
        if parse_result.disposition is ParseDisposition.FAILED:
            return ParserServiceResult(
                parse_result=parse_result,
                promotion_allowed=False,
                external_processing_allowed=False,
                governance_detail=parse_result.detail,
            )
        extracted_texts = tuple(
            element.text
            for element in parse_result.elements
            if element.text and element.text.strip()
        )
        governance_result = evaluate_extraction_governance(
            governance,
            extracted_texts=extracted_texts,
            scan_evidence_current=scan_evidence_current,
        )
        return ParserServiceResult(
            parse_result=parse_result,
            promotion_allowed=governance_result.promotion_allowed,
            external_processing_allowed=governance_result.external_processing.allowed,
            governance_detail=governance_result.detail,
            detector_outcomes=governance_result.detector_outcomes,
        )


def parse_object_bytes(
    payload: bytes,
    *,
    filename: str,
    content_hash: str | None = None,
    media_type: str | None = None,
    format_key: str | None = None,
    use_docker: bool | None = None,
) -> ParseResult:
    """Convenience helper for tests: parse bytes without governance."""

    digest = content_hash or hashlib.sha256(payload).hexdigest()
    base = ParserSandboxLauncher().config
    config = SandboxLaunchConfig(
        image=base.image,
        use_docker=base.use_docker if use_docker is None else use_docker,
        memory_mb=base.memory_mb,
        cpus=base.cpus,
        pids_limit=base.pids_limit,
        timeout_seconds=base.timeout_seconds,
        kill_grace_seconds=base.kill_grace_seconds,
    )
    launcher = ParserSandboxLauncher(config=config)
    return launcher.run(
        payload=payload,
        content_hash=digest,
        filename=filename,
        media_type=media_type,
        format_key=format_key,
    )


def _hash_mismatch_result(content_hash: str, format_key: str | None) -> ParseResult:
    """Return failed parse result for hash mismatch."""

    from smart_rag_core.ingestion.parser.limits import (
        CLEANING_POLICY_VERSION,
        PARSER_CONFIG_VERSION,
    )
    from smart_rag_core.ingestion.parser.types import (
        CoverageAccounting,
        ParserResourceMetrics,
    )

    return ParseResult(
        disposition=ParseDisposition.FAILED,
        format=format_key or "unknown",
        content_hash=content_hash,
        parser_version=PARSER_CONFIG_VERSION,
        cleaning_version=CLEANING_POLICY_VERSION,
        config_hash=ParseResult.stable_config_hash(
            PARSER_CONFIG_VERSION,
            CLEANING_POLICY_VERSION,
        ),
        coverage=CoverageAccounting(
            total_elements=0,
            text_elements=0,
            media_only_elements=0,
            removed_nodes=0,
            unsupported_regions=0,
            char_coverage_ratio=0.0,
        ),
        resource_metrics=ParserResourceMetrics(wall_seconds=0.0),
        detail="content hash mismatch",
    )
