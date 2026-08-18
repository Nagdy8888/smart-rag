"""Classify Phase 10 Packet 7 release-suite and assessment gates.

Packet 7 consumes committed Packets 1-6 gate matrices. It does not re-run
those pytest suites, apply Terraform, open holdout, invent a pentest
report, or promote production. A complete production-equivalent suite is
Blocked while launch-blocking managed rows remain Blocked. Committed
custody/IaC can Pass. Independent assessment stays Blocked until a real
third-party report exists. Traceability of freeze identities is supporting
only. Promotion inputs are recorded as no-go and remain pending.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from smart_rag_core.evaluation.holdout import HoldoutAccess
from smart_rag_core.release.io import (
    as_json_list,
    as_json_object,
    dump_canonical_json,
    load_json_object,
)
from smart_rag_core.release.packet2 import Classification
from smart_rag_core.release.phase10_constants import (
    ASSESSMENT_SCOPE_REQUIRED_TOKENS,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    EXTERNAL_ASSESSMENT_SCOPE,
    FAKE_ASSESSMENT_PASS_PHRASES,
    FULL_SCALE_ENVELOPE_PHRASES,
    GITHUB_WORKFLOWS_DIR,
    PACKET1_MATRIX_NAME,
    PACKET1_MATRIX_SCHEMA_VERSION,
    PACKET2_MATRIX_NAME,
    PACKET2_MATRIX_SCHEMA_VERSION,
    PACKET3_MATRIX_NAME,
    PACKET3_MATRIX_SCHEMA_VERSION,
    PACKET3_ORIGIN_ARTIFACT,
    PACKET4_MATRIX_NAME,
    PACKET4_MATRIX_SCHEMA_VERSION,
    PACKET5_MATRIX_NAME,
    PACKET5_MATRIX_SCHEMA_VERSION,
    PACKET6_MATRIX_NAME,
    PACKET6_MATRIX_SCHEMA_VERSION,
    PACKET7_ASSESSMENT_NAME,
    PACKET7_ASSESSMENT_SCHEMA_VERSION,
    PACKET7_CUSTODY_NAME,
    PACKET7_CUSTODY_SCHEMA_VERSION,
    PACKET7_FAKE_HTTP_STATUSES,
    PACKET7_LIVE_BLOCKED_KEYS,
    PACKET7_LIVE_NOT_RUN_KEYS,
    PACKET7_MATRIX_NAME,
    PACKET7_MATRIX_SCHEMA_VERSION,
    PACKET7_NEGATIVES_NAME,
    PACKET7_NEGATIVES_SCHEMA_VERSION,
    PACKET7_PROMOTION_SCHEMA_VERSION,
    PACKET7_RELATIVE,
    PACKET7_SUITE_NAME,
    PACKET7_SUITE_SCHEMA_VERSION,
    PACKET7_TRACEABILITY_NAME,
    PACKET7_TRACEABILITY_SCHEMA_VERSION,
    PARADEDB_IMAGE,
    PHASE09_CORPUS_MANIFEST,
    PHASE09_IMAGE_IDS,
    PHASE10_ARTIFACT_DIR,
    PHASE10_EVIDENCE,
    PHASE10_PHASE11_PROMOTION_MANIFEST,
    PHASE11_NO_GO_RECOMMENDATION,
    PHASE11_ROLLBACK,
    SIGNED_FULL_CHUNKS,
    SIGNED_FULL_HYBRID_VERSIONS,
    STAGING_COMPOSE_FILE,
    USER_ACCEPTANCE_REQUEST,
    VALKEY_IMAGE,
    VERCEL_PUBLIC_ENV_FILE,
    WRAPPER_RELATIVE,
)
from smart_rag_core.release.phase10_oidc import (
    Phase10OidcError,
    assert_committed_oidc_policy,
)
from smart_rag_core.release.phase10_packet1 import (
    LiveProviderProbe,
    packet1_checkbox_unchecked,
    probe_live_providers,
    wrapper_status_pending,
)
from smart_rag_core.release.phase10_packet2 import (
    packet2_checkbox_unchecked,
    review_migrations,
)
from smart_rag_core.release.phase10_packet3 import packet3_checkbox_unchecked
from smart_rag_core.release.phase10_packet4 import packet4_checkbox_unchecked
from smart_rag_core.release.phase10_packet5 import packet5_checkbox_unchecked
from smart_rag_core.release.phase10_packet6 import packet6_checkbox_unchecked
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    PolicyFinding,
    PolicyReport,
    assert_compose_policy,
    assert_vercel_public_env,
    hash_reviewed_files,
)

PACKET_MATRIX_SPECS: tuple[tuple[str, str, str], ...] = (
    ("P10-01", PACKET1_MATRIX_NAME, PACKET1_MATRIX_SCHEMA_VERSION),
    ("P10-02", PACKET2_MATRIX_NAME, PACKET2_MATRIX_SCHEMA_VERSION),
    ("P10-03", PACKET3_MATRIX_NAME, PACKET3_MATRIX_SCHEMA_VERSION),
    ("P10-04", PACKET4_MATRIX_NAME, PACKET4_MATRIX_SCHEMA_VERSION),
    ("P10-05", PACKET5_MATRIX_NAME, PACKET5_MATRIX_SCHEMA_VERSION),
    ("P10-06", PACKET6_MATRIX_NAME, PACKET6_MATRIX_SCHEMA_VERSION),
)


class Phase10Packet7GateError(RuntimeError):
    """Raised when Packet 7 classification cannot be recorded honestly."""


@dataclass(frozen=True, slots=True)
class AcceptanceRow:
    """One P10-07 or consumed P10-01-06 acceptance classification.

    Attributes:
        check: Requirement id such as ``P10-07-A``.
        classification: Honest Passed/Failed/Blocked/Not Run value.
        detail: Evidence without secrets.
    """

    check: str
    classification: Classification
    detail: str


@dataclass(frozen=True, slots=True)
class PacketMatrixRecord:
    """One committed Packets 1-6 gate matrix.

    Attributes:
        packet: Packet id such as ``P10-01``.
        schema_version: Expected schema string.
        path: Repository-relative artifact path.
        acceptance: Non-empty acceptance rows.
        image_ids: Phase 9 freeze ids recorded in the matrix.
        holdout_opened: True when the matrix opened holdout.
        wrapper_status: Recorded wrapper status.
        live_fields: Live probe keys mapped to Blocked/Not Run/Failed/Passed.
    """

    packet: str
    schema_version: str
    path: str
    acceptance: tuple[AcceptanceRow, ...]
    image_ids: dict[str, str]
    holdout_opened: bool
    wrapper_status: str
    live_fields: dict[str, str]


def _string_string_map(value: object, *, source: str) -> dict[str, str]:
    """Narrow a JSON object to string-to-string mapping.

    Args:
        value: Decoded JSON value.
        source: Label used in the error.

    Returns:
        String-keyed string map.

    Raises:
        Phase10Packet7GateError: If the value is not an object of strings.
    """

    try:
        typed = as_json_object(value, source=source)
    except ValueError as exc:
        raise Phase10Packet7GateError(f"{source} must be a JSON object") from exc
    result: dict[str, str] = {}
    for key, item in typed.items():
        if not isinstance(item, str):
            raise Phase10Packet7GateError(f"{source} field {key} must be a string")
        result[key] = item
    return result


def packet7_checkbox_unchecked(text: str) -> bool:
    """Return whether the wrapper Packet 7 checkbox is unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packet 7 remains ``[ ]``.
    """

    return (
        "7. [ ] [Run the complete release suite and an independent external "
        "security assessment" in text
    )


def all_phase10_checkboxes_unchecked(text: str) -> bool:
    """Return whether all seven Phase 10 wrapper checkboxes stay unchecked.

    Args:
        text: Wrapper markdown.

    Returns:
        True when packets 1-7 remain ``[ ]``.
    """

    return (
        packet1_checkbox_unchecked(text)
        and packet2_checkbox_unchecked(text)
        and packet3_checkbox_unchecked(text)
        and packet4_checkbox_unchecked(text)
        and packet5_checkbox_unchecked(text)
        and packet6_checkbox_unchecked(text)
        and packet7_checkbox_unchecked(text)
    )


def packet7_status_pending(text: str) -> bool:
    """Return whether the Packet 7 file frontmatter is still pending.

    Args:
        text: Packet markdown.

    Returns:
        True when ``status: pending`` is present in frontmatter.
    """

    head = text.split("---", 2)
    if len(head) < 3:
        return False
    return "status: pending" in head[1]


def claims_fake_assessment_pass(text: str) -> bool:
    """Return whether text claims a completed pentest or Critical=0.

    Args:
        text: Markdown or JSON.

    Returns:
        True when a forbidden Passed/Critical=0 pentest claim is present.
    """

    lowered = text.casefold()
    return any(phrase in lowered for phrase in FAKE_ASSESSMENT_PASS_PHRASES)


def claims_full_scale_envelope(text: str) -> bool:
    """Return whether text advertises the unsigned 10k/1M envelope.

    Args:
        text: Markdown or JSON.

    Returns:
        True when QT-CAP-001/002 10k/1M values appear.
    """

    lowered = text.casefold()
    return any(phrase in lowered for phrase in FULL_SCALE_ENVELOPE_PHRASES)


def recommendation_is_go(text: str) -> bool:
    """Return whether a recommendation promotes Phase 11.

    Args:
        text: Recommendation string.

    Returns:
        True when the text is a Phase 11 go without ``no-go``.
    """

    lowered = text.casefold()
    if "no-go" in lowered:
        return False
    return "go for phase 11" in lowered


def freeze_image_ids_match(image_ids: Mapping[str, str]) -> bool:
    """Return whether recorded image ids match the Phase 9 freeze.

    Args:
        image_ids: Candidate image digest map.

    Returns:
        True when every freeze service matches ``PHASE09_IMAGE_IDS``.
    """

    return dict(image_ids) == dict(PHASE09_IMAGE_IDS)


def fake_origin_http_claimed(payload: Mapping[str, object]) -> bool:
    """Return whether live origin 200/403 was invented without CDN proof.

    Args:
        payload: ``packet3-origin.json`` object.

    Returns:
        True when an HTTP 200 or 403 is recorded while live requests are
        not Passed.
    """

    live = str(payload.get("live_requests") or "")
    rows = as_json_list(payload.get("request_matrix"), source="packet3-origin-matrix")
    for item in rows:
        row = as_json_object(item, source="packet3-origin-row")
        status = row.get("http_status")
        if status in PACKET7_FAKE_HTTP_STATUSES and live != "Passed":
            return True
        classification = str(row.get("classification") or "")
        if status in PACKET7_FAKE_HTTP_STATUSES and classification == "Passed":
            return True
    return False


def blocked_acceptance_rows(
    matrices: Sequence[PacketMatrixRecord],
) -> tuple[AcceptanceRow, ...]:
    """Return every Blocked acceptance row from Packets 1-6.

    Args:
        matrices: Loaded gate matrices.

    Returns:
        Blocked rows in packet order.
    """

    rows: list[AcceptanceRow] = []
    for matrix in matrices:
        for row in matrix.acceptance:
            if row.classification == "Blocked":
                rows.append(row)
    return tuple(rows)


def live_blocked_fields(
    matrices: Sequence[PacketMatrixRecord],
) -> tuple[dict[str, str], ...]:
    """Return live probe fields that are Blocked or Not Run.

    Args:
        matrices: Loaded gate matrices.

    Returns:
        Packet, field, and state mappings without secrets.
    """

    items: list[dict[str, str]] = []
    tracked = set(PACKET7_LIVE_BLOCKED_KEYS) | set(PACKET7_LIVE_NOT_RUN_KEYS)
    for matrix in matrices:
        for key, value in matrix.live_fields.items():
            if key not in tracked:
                continue
            if value in {"Blocked", "Not Run", "Failed"}:
                items.append({"packet": matrix.packet, "field": key, "state": value})
    return tuple(items)


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises
            ``Phase10Packet7GateError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except Phase10Packet7GateError as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def assert_holdout_sealed(repo_root: Path) -> None:
    """Fail when holdout is open in settings or corpus freeze.

    Args:
        repo_root: Repository root.

    Raises:
        Phase10Packet7GateError: If holdout is open.
    """

    if HoldoutAccess.from_settings().allowed:
        raise Phase10Packet7GateError("SMART_RAG_HOLDOUT_ACCESS must not be true")
    try:
        corpus = load_json_object(repo_root / PHASE09_CORPUS_MANIFEST)
    except (OSError, ValueError) as exc:
        raise Phase10Packet7GateError("Phase 9 corpus manifest is unavailable") from exc
    if corpus.get("holdout_opened") is True:
        raise Phase10Packet7GateError("corpus holdout_opened must remain false")


def assert_no_fake_assessment(text: str, *, source: str) -> None:
    """Reject invented pentest Passed or Critical=0 claims.

    Args:
        text: Document or JSON text.
        source: Label used in the error.

    Raises:
        Phase10Packet7GateError: If a fake assessment pass is present.
    """

    if claims_fake_assessment_pass(text):
        raise Phase10Packet7GateError(
            f"{source} claims a completed pentest or Critical=0"
        )


def assert_scope_doc(text: str) -> None:
    """Require the scope-only assessment document and reject a fake report.

    Args:
        text: Scope markdown.

    Raises:
        Phase10Packet7GateError: If required tokens, status, or honesty
            language is missing, or a Passed pentest is claimed.
    """

    assert_no_fake_assessment(text, source=EXTERNAL_ASSESSMENT_SCOPE)
    lowered = text.casefold()
    if "status: not-run" not in lowered and "status: not run" not in lowered:
        raise Phase10Packet7GateError(
            "assessment scope frontmatter must record status not-run"
        )
    missing = [
        token for token in ASSESSMENT_SCOPE_REQUIRED_TOKENS if token not in lowered
    ]
    if missing:
        raise Phase10Packet7GateError(
            "assessment scope missing required tokens: " + ", ".join(missing)
        )
    if "```mermaid" not in text:
        raise Phase10Packet7GateError("assessment scope must include a Mermaid diagram")


def assert_no_full_scale_claim(text: str, *, source: str) -> None:
    """Reject unsigned 10k/1M envelope advertising.

    Args:
        text: Manifest or evidence text.
        source: Label used in the error.

    Raises:
        Phase10Packet7GateError: If 10k/1M values are advertised.
    """

    if claims_full_scale_envelope(text):
        raise Phase10Packet7GateError(f"{source} advertises 10k/1M")


def assert_wrapper_pending_unchecked(wrapper: str, packet: str) -> None:
    """Require wrapper pending and all seven checkboxes unchecked.

    Args:
        wrapper: Phase 10 wrapper markdown.
        packet: Packet 7 markdown.

    Raises:
        Phase10Packet7GateError: If the wrapper is complete or a checkbox
            is checked.
    """

    if not wrapper_status_pending(wrapper):
        raise Phase10Packet7GateError("Phase 10 wrapper must remain status: pending")
    if not all_phase10_checkboxes_unchecked(wrapper):
        raise Phase10Packet7GateError(
            "all seven Phase 10 checkboxes must stay unchecked"
        )
    if not packet7_status_pending(packet):
        raise Phase10Packet7GateError("Packet 7 file must remain status: pending")


def assert_acceptance_request(text: str, *, source: str) -> None:
    """Require the exact user-acceptance request string.

    Args:
        text: Evidence or manifest text.
        source: Label used in the error.

    Raises:
        Phase10Packet7GateError: If the request text is missing.
    """

    if USER_ACCEPTANCE_REQUEST not in text:
        raise Phase10Packet7GateError(
            f"{source} must contain the exact user-acceptance request"
        )


def load_packet_matrix(
    repo_root: Path,
    *,
    packet: str,
    name: str,
    schema_version: str,
) -> PacketMatrixRecord:
    """Load and validate one Packets 1-6 gate matrix.

    Args:
        repo_root: Repository root.
        packet: Expected packet id.
        name: Artifact file name.
        schema_version: Expected schema version.

    Returns:
        Typed matrix record.

    Raises:
        Phase10Packet7GateError: If the file is missing, empty, or schema
            wrong.
    """

    relative = f"{PHASE10_ARTIFACT_DIR}/{name}"
    path = repo_root / relative
    try:
        payload = load_json_object(path)
    except (OSError, ValueError) as exc:
        raise Phase10Packet7GateError(
            f"packet matrix missing or invalid: {relative}"
        ) from exc
    if payload.get("schema_version") != schema_version:
        raise Phase10Packet7GateError(f"{relative} schema_version is wrong")
    if payload.get("packet") != packet:
        raise Phase10Packet7GateError(f"{relative} packet id drifted")
    raw_rows = as_json_list(payload.get("acceptance"), source=f"{relative} acceptance")
    if not raw_rows:
        raise Phase10Packet7GateError(f"{relative} acceptance is empty")
    rows: list[AcceptanceRow] = []
    for item in raw_rows:
        row = as_json_object(item, source=f"{relative} row")
        check = str(row.get("check") or "")
        classification = str(row.get("classification") or "")
        detail = str(row.get("detail") or "")
        if not check or classification not in {
            "Passed",
            "Failed",
            "Blocked",
            "Not Run",
        }:
            raise Phase10Packet7GateError(f"{relative} row schema is wrong")
        typed: Classification
        if classification == "Passed":
            typed = "Passed"
        elif classification == "Failed":
            typed = "Failed"
        elif classification == "Blocked":
            typed = "Blocked"
        else:
            typed = "Not Run"
        rows.append(
            AcceptanceRow(
                check=check,
                classification=typed,
                detail=detail,
            )
        )
    expected_checks = {f"{packet}-{suffix}" for suffix in "ABCDE"}
    present_checks = {row.check for row in rows}
    if present_checks != expected_checks:
        raise Phase10Packet7GateError(
            f"{relative} must contain {packet}-A through E; found "
            + ", ".join(sorted(present_checks))
        )
    image_ids = _string_string_map(
        payload.get("phase9_image_ids"), source=f"{relative} phase9_image_ids"
    )
    if payload.get("holdout_opened") is True:
        raise Phase10Packet7GateError(f"{relative} opened holdout")
    live_fields: dict[str, str] = {}
    for key, value in payload.items():
        if not key.startswith("live_"):
            continue
        if isinstance(value, str):
            live_fields[key] = value
    return PacketMatrixRecord(
        packet=packet,
        schema_version=schema_version,
        path=relative,
        acceptance=tuple(rows),
        image_ids=image_ids,
        holdout_opened=payload.get("holdout_opened") is True,
        wrapper_status=str(payload.get("wrapper_status") or ""),
        live_fields=live_fields,
    )


def load_packet_matrices(repo_root: Path) -> tuple[PacketMatrixRecord, ...]:
    """Load every Packets 1-6 gate matrix.

    Args:
        repo_root: Repository root.

    Returns:
        Six typed matrix records.

    Raises:
        Phase10Packet7GateError: If any matrix is missing, empty, or
            schema wrong.
    """

    return tuple(
        load_packet_matrix(
            repo_root,
            packet=packet,
            name=name,
            schema_version=schema,
        )
        for packet, name, schema in PACKET_MATRIX_SPECS
    )


def assert_freeze_identities(matrices: Sequence[PacketMatrixRecord]) -> None:
    """Require every matrix freeze map to match Phase 9 image ids.

    Args:
        matrices: Loaded gate matrices.

    Raises:
        Phase10Packet7GateError: On digest drift.
    """

    for matrix in matrices:
        if not freeze_image_ids_match(matrix.image_ids):
            raise Phase10Packet7GateError(
                f"{matrix.path} Phase 9 image ids drifted from the freeze"
            )


def assert_no_fake_origin_http(repo_root: Path) -> None:
    """Reject invented CDN 200/403 while live origin proof is Blocked.

    Args:
        repo_root: Repository root.

    Raises:
        Phase10Packet7GateError: If fake HTTP statuses are recorded.
    """

    try:
        payload = load_json_object(repo_root / PACKET3_ORIGIN_ARTIFACT)
    except (OSError, ValueError) as exc:
        raise Phase10Packet7GateError("packet3-origin.json is unavailable") from exc
    if fake_origin_http_claimed(payload):
        raise Phase10Packet7GateError("fake origin HTTP 200/403 is Failed")


def assert_packet7_custody_policy(repo_root: Path) -> PolicyReport:
    """Assert committed OIDC, private ports, ParadeDB pin, and expand/contract.

    Live OIDC assume is not required for this policy Pass. Fake origin
    200/403 fails.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10Packet7GateError: If required files are missing or any
            check fails.
    """

    compose = (repo_root / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    vercel = load_json_object(repo_root / VERCEL_PUBLIC_ENV_FILE)

    def oidc() -> None:
        """Run committed OIDC policy.

        Raises:
            Phase10Packet7GateError: If OIDC/workflow policy fails.
        """

        try:
            report = assert_committed_oidc_policy(repo_root)
        except Phase10OidcError as exc:
            raise Phase10Packet7GateError(str(exc)) from exc
        if not report.passed:
            raise Phase10Packet7GateError("OIDC custody policy Failed")

    def compose_ports() -> None:
        """Assert private ports and digest pins.

        Raises:
            Phase10Packet7GateError: If Compose policy fails.
        """

        try:
            assert_compose_policy(compose)
        except Phase10TopologyError as exc:
            raise Phase10Packet7GateError(str(exc)) from exc

    def vercel_env() -> None:
        """Assert Vercel public env only.

        Raises:
            Phase10Packet7GateError: If secret keys are present.
        """

        try:
            assert_vercel_public_env(vercel)
        except Phase10TopologyError as exc:
            raise Phase10Packet7GateError(str(exc)) from exc

    def contractions() -> None:
        """Assert expand/contract violations are absent.

        Raises:
            Phase10Packet7GateError: If contraction DDL exists.
        """

        review = review_migrations(repo_root)
        if not review.contraction_absent:
            raise Phase10Packet7GateError(
                "expand/contract find_migration_violations found contraction"
            )

    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("oidc_no_long_lived", oidc),
        ("private_ports_digest_pin", compose_ports),
        ("vercel_public_only", vercel_env),
        ("expand_contract", contractions),
        ("no_fake_http", lambda: assert_no_fake_origin_http(repo_root)),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed: Sequence[Path] = (
        repo_root / STAGING_COMPOSE_FILE,
        repo_root / VERCEL_PUBLIC_ENV_FILE,
        repo_root / PACKET3_ORIGIN_ARTIFACT,
        repo_root / EXTERNAL_ASSESSMENT_SCOPE,
    )
    report = PolicyReport(
        passed=all(item.passed for item in findings),
        findings=findings,
        iac_sha256=hash_reviewed_files(reviewed),
    )
    if not report.passed:
        failed = [item.check for item in findings if not item.passed]
        details = "; ".join(
            f"{item.check}: {item.detail}" for item in findings if not item.passed
        )
        raise Phase10Packet7GateError(
            "Packet 7 custody policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report


def classify_p1007_a(
    *,
    matrices_ok: bool,
    blocked_launch_rows: bool,
    zero_tests: bool,
    claimed_suite_passed: bool,
) -> Classification:
    """Classify the complete production-equivalent suite.

    Args:
        matrices_ok: Packets 1-6 matrices loaded with nonempty rows.
        blocked_launch_rows: Any launch-blocking managed row is Blocked.
        zero_tests: Packet 7 collected zero tests.
        claimed_suite_passed: Evidence claimed the suite Passed.

    Returns:
        ``Failed`` on missing matrices, zero tests, or a fake suite Pass.
        ``Blocked`` when managed launch rows remain Blocked. ``Passed``
        only when every managed row Passed.
    """

    if zero_tests or not matrices_ok or claimed_suite_passed:
        return "Failed"
    if blocked_launch_rows:
        return "Blocked"
    return "Passed"


def classify_p1007_b(
    *,
    custody_passed: bool,
    fake_http: bool,
    live_oidc_state: str,
) -> Classification:
    """Classify committed custody/IaC with live OIDC remaining Blocked.

    Args:
        custody_passed: OIDC, private ports, ParadeDB pin, expand/contract,
            and Vercel public-env policy.
        fake_http: Invented origin 200/403.
        live_oidc_state: Honest live assume-role probe.

    Returns:
        ``Failed`` on policy miss, fake HTTP, or a failed live probe.
        ``Passed`` for committed custody even when live OIDC is Blocked.
    """

    if not custody_passed or fake_http or live_oidc_state == "Failed":
        return "Failed"
    return "Passed"


def classify_p1007_c(
    *,
    scope_ok: bool,
    assessment_run: bool,
    invented_pass: bool,
) -> Classification:
    """Classify independent external assessment.

    Args:
        scope_ok: Scope-only document exists with required tokens.
        assessment_run: True only after a real third-party report.
        invented_pass: Fake Passed/Critical=0 pentest claim.

    Returns:
        ``Failed`` on invented Pass or missing scope. ``Blocked`` when
        the assessment was not run. ``Passed`` only after independent
        Critical/High-zero retest.
    """

    if invented_pass or not scope_ok:
        return "Failed"
    if not assessment_run:
        return "Blocked"
    return "Passed"


def classify_p1007_d(
    *,
    freeze_match: bool,
    suite_blocked: bool,
    assessment_blocked: bool,
    live_blocked: bool,
) -> Classification:
    """Classify one-artifact-set proof of all managed gates.

    Args:
        freeze_match: Freeze ids match Phase 9.
        suite_blocked: P10-07-A is Blocked.
        assessment_blocked: P10-07-C is Blocked.
        live_blocked: Any Packets 1-6 live probe is Blocked.

    Returns:
        ``Failed`` on digest drift. ``Blocked`` while A/C or live managed
        rows remain Blocked. ``Passed`` only when every managed gate
        Passed.
    """

    if not freeze_match:
        return "Failed"
    if suite_blocked or assessment_blocked or live_blocked:
        return "Blocked"
    return "Passed"


def classify_p1007_e(
    *,
    manifest_ok: bool,
    wrapper_pending: bool,
    all_unchecked: bool,
    nogo: bool,
    envelope_ok: bool,
    holdout_closed: bool,
    acceptance_request: bool,
) -> Classification:
    """Classify Phase 11 promotion inputs remaining pending.

    Args:
        manifest_ok: Promotion manifest exists with freeze ids.
        wrapper_pending: Wrapper frontmatter is pending.
        all_unchecked: All seven checkboxes remain ``[ ]``.
        nogo: Recommendation is no-go for Phase 11.
        envelope_ok: Envelope stays 8/16/15.
        holdout_closed: Holdout remains denied.
        acceptance_request: Exact user-acceptance request is present.

    Returns:
        ``Passed`` only when every pending/no-go condition holds.
        Otherwise ``Failed``.
    """

    if not (
        manifest_ok
        and wrapper_pending
        and all_unchecked
        and nogo
        and envelope_ok
        and holdout_closed
        and acceptance_request
    ):
        return "Failed"
    return "Passed"


def classify_packet7(
    *,
    matrices: Sequence[PacketMatrixRecord],
    custody: PolicyReport | None,
    live: LiveProviderProbe,
    fake_http: bool,
    scope_ok: bool,
    assessment_run: bool,
    invented_assessment_pass: bool,
    freeze_match: bool,
    manifest_ok: bool,
    wrapper_pending: bool,
    all_unchecked: bool,
    nogo: bool,
    envelope_ok: bool,
    holdout_closed: bool,
    acceptance_request: bool,
    claimed_suite_passed: bool = False,
    zero_tests: bool = False,
) -> tuple[AcceptanceRow, ...]:
    """Classify P10-07-A through E from committed evidence.

    Args:
        matrices: Packets 1-6 matrices.
        custody: Custody/IaC policy report.
        live: Provider probe. Never an apply or login.
        fake_http: Invented origin 200/403.
        scope_ok: Scope document passed token checks.
        assessment_run: Real third-party assessment exists.
        invented_assessment_pass: Fake pentest Pass.
        freeze_match: Image ids match the freeze.
        manifest_ok: Promotion manifest exists.
        wrapper_pending: Wrapper is pending.
        all_unchecked: All seven checkboxes unchecked.
        nogo: Recommendation is no-go.
        envelope_ok: Envelope stays 8/16/15.
        holdout_closed: Holdout denied.
        acceptance_request: Exact acceptance request present.
        claimed_suite_passed: Fake complete-suite Pass.
        zero_tests: Packet 7 collected zero tests.

    Returns:
        Five acceptance rows.
    """

    blocked_rows = blocked_acceptance_rows(matrices)
    live_blocked = live_blocked_fields(matrices)
    matrices_ok = bool(matrices) and all(matrix.acceptance for matrix in matrices)
    class_a = classify_p1007_a(
        matrices_ok=matrices_ok,
        blocked_launch_rows=bool(blocked_rows) or bool(live_blocked),
        zero_tests=zero_tests,
        claimed_suite_passed=claimed_suite_passed,
    )
    class_c = classify_p1007_c(
        scope_ok=scope_ok,
        assessment_run=assessment_run,
        invented_pass=invented_assessment_pass,
    )
    class_b = classify_p1007_b(
        custody_passed=custody.passed if custody is not None else False,
        fake_http=fake_http,
        live_oidc_state=live.apply_state,
    )
    class_d = classify_p1007_d(
        freeze_match=freeze_match,
        suite_blocked=class_a == "Blocked",
        assessment_blocked=class_c == "Blocked",
        live_blocked=bool(live_blocked),
    )
    class_e = classify_p1007_e(
        manifest_ok=manifest_ok,
        wrapper_pending=wrapper_pending,
        all_unchecked=all_unchecked,
        nogo=nogo,
        envelope_ok=envelope_ok,
        holdout_closed=holdout_closed,
        acceptance_request=acceptance_request,
    )
    blocked_ids = ", ".join(row.check for row in blocked_rows)
    return (
        AcceptanceRow(
            check="P10-07-A",
            classification=class_a,
            detail=(
                "Packets 1-6 local policy gates collected nonzero tests and "
                "wrote artifacts, but launch-blocking managed rows remain "
                f"Blocked ({blocked_ids}). A complete production-equivalent "
                "suite did not pass. Packet 7 consumes committed JSON and "
                "does not re-run Packets 1-6 pytest."
            ),
        ),
        AcceptanceRow(
            check="P10-07-B",
            classification=class_b,
            detail=(
                "Committed custody/IaC Passed: OIDC with no long-lived GitHub "
                "secrets, private ports, digest-pinned ParadeDB, expand/contract "
                "find_migration_violations, Vercel public env only. Live OIDC "
                f"assume remains {live.apply_state} ({live.apply_reason}). "
                "Fake origin 200/403 is Failed."
            ),
        ),
        AcceptanceRow(
            check="P10-07-C",
            classification=class_c,
            detail=(
                "No independent third-party pentest/external security review "
                "report exists. Scope is documented as not run. Trivy is image "
                "scan, not Packet 7-C. Critical=0 was not claimed from an "
                "assessment that did not happen."
            ),
        ),
        AcceptanceRow(
            check="P10-07-D",
            classification=class_d,
            detail=(
                "One exact artifact set does not prove all managed gates while "
                "P10-07-A/C and Packets 1-6 live rows remain Blocked. "
                "Traceability of committed packet 1-6 freeze identities is "
                "supporting. Digest drift versus Phase 9 freeze is Failed."
            ),
        ),
        AcceptanceRow(
            check="P10-07-E",
            classification=class_e,
            detail=(
                "Promotion inputs recorded. Wrapper pending. All seven "
                "checkboxes unchecked. Recommendation is no-go for Phase 11. "
                f"Envelope QT-CAP-001-P9={ENVELOPE_HYBRID_VERSIONS} / "
                f"QT-CAP-002-P9={ENVELOPE_CHUNKS} / "
                f"QT-CAP-005-P8={ENVELOPE_GRAPH_VERSIONS}. Holdout closed. "
                + USER_ACCEPTANCE_REQUEST
            ),
        ),
    )


def envelope_payload() -> dict[str, int]:
    """Return the signed reduced envelope mapping.

    Returns:
        QT-CAP identifiers mapped to 8/16/15.
    """

    return {
        "QT-CAP-001-P9": ENVELOPE_HYBRID_VERSIONS,
        "QT-CAP-002-P9": ENVELOPE_CHUNKS,
        "QT-CAP-005-P8": ENVELOPE_GRAPH_VERSIONS,
    }


def build_promotion_manifest(
    *,
    rows: Sequence[AcceptanceRow],
    matrices: Sequence[PacketMatrixRecord],
) -> dict[str, object]:
    """Build the Phase 11 no-go promotion manifest.

    Args:
        rows: Packet 7 acceptance rows.
        matrices: Packets 1-6 matrices.

    Returns:
        Canonical manifest mapping without secrets.
    """

    blocked = [
        {"check": row.check, "classification": row.classification, "detail": row.detail}
        for matrix in matrices
        for row in matrix.acceptance
        if row.classification == "Blocked"
    ]
    blocked.extend(
        {
            "check": row.check,
            "classification": row.classification,
            "detail": row.detail,
        }
        for row in rows
        if row.classification == "Blocked"
    )
    return {
        "schema_version": PACKET7_PROMOTION_SCHEMA_VERSION,
        "recommendation": PHASE11_NO_GO_RECOMMENDATION,
        "rollback": PHASE11_ROLLBACK,
        "wrapper_status": "pending",
        "packet_checkboxes": "unchecked",
        "holdout_opened": False,
        "terraform_apply": False,
        "aws_login": False,
        "production_promotion": False,
        "user_acceptance_request": USER_ACCEPTANCE_REQUEST,
        "envelope": envelope_payload(),
        "signed_full_hybrid_not_advertised": SIGNED_FULL_HYBRID_VERSIONS,
        "signed_full_chunks_not_advertised": SIGNED_FULL_CHUNKS,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "paradedb_image": PARADEDB_IMAGE,
        "valkey_image": VALKEY_IMAGE,
        "blocked_phase11_rows": blocked,
        "live_blocked": list(live_blocked_fields(matrices)),
        "acceptance": [
            {
                "check": row.check,
                "classification": row.classification,
                "detail": row.detail,
            }
            for row in rows
        ],
    }


def validate_promotion_manifest(payload: Mapping[str, object]) -> None:
    """Require the committed promotion manifest to stay no-go.

    Args:
        payload: Promotion manifest object.

    Raises:
        Phase10Packet7GateError: If freeze, envelope, recommendation, or
            acceptance-request fields drifted.
    """

    if payload.get("schema_version") != PACKET7_PROMOTION_SCHEMA_VERSION:
        raise Phase10Packet7GateError("promotion manifest schema_version drifted")
    recommendation = str(payload.get("recommendation") or "")
    if recommendation != PHASE11_NO_GO_RECOMMENDATION or recommendation_is_go(
        recommendation
    ):
        raise Phase10Packet7GateError("promotion recommendation must be no-go")
    if payload.get("wrapper_status") != "pending":
        raise Phase10Packet7GateError(
            "promotion manifest wrapper_status must be pending"
        )
    if payload.get("holdout_opened") is True:
        raise Phase10Packet7GateError("promotion manifest must not open holdout")
    if payload.get("terraform_apply") is True or payload.get("aws_login") is True:
        raise Phase10Packet7GateError("promotion manifest must not apply or login")
    if payload.get("production_promotion") is True:
        raise Phase10Packet7GateError("promotion manifest must not promote production")
    envelope = as_json_object(payload.get("envelope"), source="promotion envelope")
    if envelope != envelope_payload():
        raise Phase10Packet7GateError("promotion envelope must remain 8/16/15")
    dumped = str(payload)
    assert_no_full_scale_claim(dumped, source="promotion manifest")
    assert_acceptance_request(
        str(payload.get("user_acceptance_request") or ""),
        source="promotion manifest",
    )
    image_ids = _string_string_map(
        payload.get("phase9_image_ids"), source="promotion freeze ids"
    )
    if not freeze_image_ids_match(image_ids):
        raise Phase10Packet7GateError("promotion freeze ids drifted")
    if payload.get("paradedb_image") != PARADEDB_IMAGE:
        raise Phase10Packet7GateError("promotion ParadeDB digest drifted")
    if payload.get("valkey_image") != VALKEY_IMAGE:
        raise Phase10Packet7GateError("promotion Valkey digest drifted")
    blocked = as_json_list(
        payload.get("blocked_phase11_rows"), source="blocked_phase11_rows"
    )
    if not blocked:
        raise Phase10Packet7GateError(
            "promotion manifest must list Blocked Phase 11 rows"
        )


def scan_repo_for_fake_assessment(repo_root: Path) -> None:
    """Scan committed docs/artifacts for invented pentest Pass claims.

    Args:
        repo_root: Repository root.

    Raises:
        Phase10Packet7GateError: If a fake assessment Pass is present.
    """

    paths = [
        repo_root / EXTERNAL_ASSESSMENT_SCOPE,
        repo_root / PHASE10_EVIDENCE,
        repo_root / PHASE10_PHASE11_PROMOTION_MANIFEST,
        *(repo_root / PHASE10_ARTIFACT_DIR).glob("packet7-*.json"),
        *(repo_root / "docs/security").glob("*.md"),
    ]
    for path in paths:
        if not path.is_file():
            continue
        assert_no_fake_assessment(
            path.read_text(encoding="utf-8"), source=str(path.as_posix())
        )


def negatives_catalog() -> tuple[dict[str, str], ...]:
    """Return the Packet 7 negative cases exercised by unit tests.

    Returns:
        Machine-readable negative catalog without secret values.
    """

    exercise = "tests/unit/test_phase10_packet7.py"
    expected = "Phase10Packet7GateError"
    return (
        {
            "case": "fake_pentest_passed",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "checkbox_checked",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "wrapper_complete",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "digest_drift",
            "expected": "Failed",
            "exercise": exercise,
        },
        {
            "case": "ten_k_claim",
            "expected": expected,
            "exercise": exercise,
        },
        {
            "case": "zero_packet_matrices",
            "expected": "Failed",
            "exercise": exercise,
        },
        {
            "case": "holdout_opened",
            "expected": expected,
            "exercise": exercise,
        },
    )


def write_packet7_artifacts(
    repo_root: Path,
    *,
    policy: PolicyReport,
    live: LiveProviderProbe,
    rows: Sequence[AcceptanceRow],
    matrices: Sequence[PacketMatrixRecord],
    packet7_subset: Mapping[str, object],
) -> dict[str, Path]:
    """Write Packet 7 JSON artifacts and the Phase 11 no-go manifest.

    Args:
        repo_root: Repository root.
        policy: Custody policy report.
        live: Provider probe.
        rows: Acceptance classifications.
        matrices: Packets 1-6 matrices.
        packet7_subset: Packet 7 pytest collection counts.

    Returns:
        Artifact name to path mapping.

    Side Effects:
        Overwrites files under ``docs/deployment/phase-10/``.
    """

    artifact_dir = repo_root / PHASE10_ARTIFACT_DIR
    blocked = blocked_acceptance_rows(matrices)
    live_blocked = live_blocked_fields(matrices)
    promotion = build_promotion_manifest(rows=rows, matrices=matrices)
    matrix: dict[str, object] = {
        "schema_version": PACKET7_MATRIX_SCHEMA_VERSION,
        "packet": "P10-07",
        "wrapper_status": "pending",
        "packet1_checkbox": "unchecked",
        "packet2_checkbox": "unchecked",
        "packet3_checkbox": "unchecked",
        "packet4_checkbox": "unchecked",
        "packet5_checkbox": "unchecked",
        "packet6_checkbox": "unchecked",
        "packet7_checkbox": "unchecked",
        "holdout_opened": False,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "paradedb_image": PARADEDB_IMAGE,
        "valkey_image": VALKEY_IMAGE,
        "envelope": envelope_payload(),
        "recommendation": PHASE11_NO_GO_RECOMMENDATION,
        "policy": "Passed" if policy.passed else "Failed",
        "policy_sha256": policy.iac_sha256,
        "live_oidc_assume": live.apply_state,
        "independent_assessment": "not_run",
        "packet7_subset": dict(packet7_subset),
        "acceptance": [
            {
                "check": row.check,
                "classification": row.classification,
                "detail": row.detail,
            }
            for row in rows
        ],
        "user_acceptance_request": USER_ACCEPTANCE_REQUEST,
    }
    suite_out: dict[str, object] = {
        "schema_version": PACKET7_SUITE_SCHEMA_VERSION,
        "consumed_pytest_packets_1_6": False,
        "consumed_committed_json": True,
        "matrices": [
            {
                "packet": item.packet,
                "path": item.path,
                "schema_version": item.schema_version,
                "acceptance": [
                    {
                        "check": row.check,
                        "classification": row.classification,
                    }
                    for row in item.acceptance
                ],
            }
            for item in matrices
        ],
        "blocked_rows": [row.check for row in blocked],
        "complete_production_equivalent_suite": "Blocked",
    }
    custody_out: dict[str, object] = {
        "schema_version": PACKET7_CUSTODY_SCHEMA_VERSION,
        "policy": "Passed" if policy.passed else "Failed",
        "policy_sha256": policy.iac_sha256,
        "oidc_no_long_lived_github_secrets": True,
        "private_ports": True,
        "paradedb_digest_pinned": True,
        "expand_contract_find_migration_violations": True,
        "vercel_public_env_only": True,
        "fake_origin_http_200_403": False,
        "live_oidc_assume": live.apply_state,
        "live_reason": live.apply_reason,
        "findings": [
            {"check": item.check, "passed": item.passed, "detail": item.detail}
            for item in policy.findings
        ],
    }
    assessment_out: dict[str, object] = {
        "schema_version": PACKET7_ASSESSMENT_SCHEMA_VERSION,
        "kind": "scope_only",
        "status": "not_run",
        "report_path": None,
        "independent_assessor": None,
        "critical_open": None,
        "high_open": None,
        "medium_owned_dated": None,
        "trivy_is_pentest": False,
        "trivy_note": "Phase 9 tar Trivy is image scan, not Packet 7-C",
        "scope_doc": EXTERNAL_ASSESSMENT_SCOPE,
        "synthetic_only": True,
        "long_lived_credentials": False,
    }
    trace_out: dict[str, object] = {
        "schema_version": PACKET7_TRACEABILITY_SCHEMA_VERSION,
        "proves_all_managed_gates": False,
        "freeze_match": True,
        "phase9_image_ids": dict(PHASE09_IMAGE_IDS),
        "paradedb_image": PARADEDB_IMAGE,
        "valkey_image": VALKEY_IMAGE,
        "packet_identities": [
            {
                "packet": item.packet,
                "path": item.path,
                "image_ids": item.image_ids,
            }
            for item in matrices
        ],
        "live_blocked": list(live_blocked),
        "p10_07_a": next(row.classification for row in rows if row.check == "P10-07-A"),
        "p10_07_c": next(row.classification for row in rows if row.check == "P10-07-C"),
    }
    negatives_out: dict[str, object] = {
        "schema_version": PACKET7_NEGATIVES_SCHEMA_VERSION,
        "cases": list(negatives_catalog()),
    }
    paths = {
        PACKET7_MATRIX_NAME: artifact_dir / PACKET7_MATRIX_NAME,
        PACKET7_SUITE_NAME: artifact_dir / PACKET7_SUITE_NAME,
        PACKET7_CUSTODY_NAME: artifact_dir / PACKET7_CUSTODY_NAME,
        PACKET7_ASSESSMENT_NAME: artifact_dir / PACKET7_ASSESSMENT_NAME,
        PACKET7_TRACEABILITY_NAME: artifact_dir / PACKET7_TRACEABILITY_NAME,
        PACKET7_NEGATIVES_NAME: artifact_dir / PACKET7_NEGATIVES_NAME,
        "promotion": repo_root / PHASE10_PHASE11_PROMOTION_MANIFEST,
    }
    dump_canonical_json(matrix, paths[PACKET7_MATRIX_NAME])
    dump_canonical_json(suite_out, paths[PACKET7_SUITE_NAME])
    dump_canonical_json(custody_out, paths[PACKET7_CUSTODY_NAME])
    dump_canonical_json(assessment_out, paths[PACKET7_ASSESSMENT_NAME])
    dump_canonical_json(trace_out, paths[PACKET7_TRACEABILITY_NAME])
    dump_canonical_json(negatives_out, paths[PACKET7_NEGATIVES_NAME])
    dump_canonical_json(promotion, paths["promotion"])
    return paths


def evaluate_packet7(
    repo_root: Path,
    *,
    packet7_tests_ok: bool,
) -> tuple[
    PolicyReport,
    LiveProviderProbe,
    tuple[PacketMatrixRecord, ...],
    tuple[AcceptanceRow, ...],
]:
    """Run committed Packet 7 policy plus probes and classify P10-07.

    Does not re-run Packets 1-6 pytest. Wrapper and all seven checkboxes
    stay pending/unchecked. Independent assessment stays not run.

    Args:
        repo_root: Repository root.
        packet7_tests_ok: Nonzero Packet 7 tests with no skip.

    Returns:
        Custody policy, live probe, consumed matrices, and acceptance rows.

    Raises:
        Phase10Packet7GateError: If policy fails, matrices are missing,
            the wrapper was marked complete, a checkbox was checked, or
            a fake pentest Pass exists.
    """

    wrapper = (repo_root / WRAPPER_RELATIVE).read_text(encoding="utf-8")
    packet = (repo_root / PACKET7_RELATIVE).read_text(encoding="utf-8")
    assert_wrapper_pending_unchecked(wrapper, packet)
    workflow = (repo_root / GITHUB_WORKFLOWS_DIR / "pr-fast.yml").read_text(
        encoding="utf-8"
    )
    if "check_phase10_packet7.py" in workflow:
        raise Phase10Packet7GateError("Packet 7 gate must not be added to pr-fast.yml")
    if not packet7_tests_ok:
        raise Phase10Packet7GateError("Packet 7 suite collected zero tests or skipped")
    assert_holdout_sealed(repo_root)
    scan_repo_for_fake_assessment(repo_root)
    scope_text = (repo_root / EXTERNAL_ASSESSMENT_SCOPE).read_text(encoding="utf-8")
    assert_scope_doc(scope_text)
    evidence = (repo_root / PHASE10_EVIDENCE).read_text(encoding="utf-8")
    assert_acceptance_request(evidence, source=PHASE10_EVIDENCE)
    assert_no_full_scale_claim(evidence, source=PHASE10_EVIDENCE)
    matrices = load_packet_matrices(repo_root)
    assert_freeze_identities(matrices)
    policy = assert_packet7_custody_policy(repo_root)
    live = probe_live_providers()
    origin = load_json_object(repo_root / PACKET3_ORIGIN_ARTIFACT)
    fake_http = fake_origin_http_claimed(origin)
    promotion_path = repo_root / PHASE10_PHASE11_PROMOTION_MANIFEST
    manifest_exists = promotion_path.is_file()
    if manifest_exists:
        validate_promotion_manifest(load_json_object(promotion_path))
    rows = classify_packet7(
        matrices=matrices,
        custody=policy,
        live=live,
        fake_http=fake_http,
        scope_ok=True,
        assessment_run=False,
        invented_assessment_pass=False,
        freeze_match=True,
        manifest_ok=manifest_exists,
        wrapper_pending=True,
        all_unchecked=True,
        nogo=True,
        envelope_ok=True,
        holdout_closed=True,
        acceptance_request=True,
        zero_tests=False,
    )
    return policy, live, matrices, rows
