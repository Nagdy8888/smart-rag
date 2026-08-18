"""Parse and assert Phase 10 Packet 1 Terraform, Compose, Caddy, and inventory.

Policy checks parse committed files in Python. They do not apply Terraform,
call AWS, or treat missing live scans as Passed. Fail closed on SSH, IMDSv1,
unencrypted EBS, public private-service ports, mutable ParadeDB/Valkey
images, CloudFront timeouts other than 90 seconds, Vercel secret keys,
production data flags, missing CloudFront prefix list, hop limit other than
1, missing CachingDisabled, and host ports on private services.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from smart_rag_core.release.io import as_json_list, as_json_object, load_json_object
from smart_rag_core.release.phase10_constants import (
    ALL_VIEWER_EXCEPT_HOST_POLICY_ID,
    AWS_PROVIDER_CONSTRAINT,
    CACHING_DISABLED_POLICY_ID,
    CLOUDFRONT_PREFIX_LIST_NAME,
    ENVELOPE_CHUNKS,
    ENVELOPE_GRAPH_VERSIONS,
    ENVELOPE_HYBRID_VERSIONS,
    IMDS_HOP_LIMIT,
    IMDS_HTTP_TOKENS_REQUIRED,
    INFRA_EC2_DIR,
    INTENDED_AWS_REGION,
    INTENDED_SUPABASE_PLAN,
    INTENDED_SUPABASE_REGION,
    INTENDED_TOPOLOGY_FILE,
    LIGHTRAG_DEPLOYMENT,
    LIGHTRAG_PUBLIC_PORTS,
    ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
    ORIGIN_READ_TIMEOUT_SECONDS,
    PACKET8_HOST_PORTS,
    PARADEDB_DIGEST,
    PARADEDB_IMAGE,
    PHASE09_CORPUS_MANIFEST,
    PHASE09_IMAGE_IDS,
    PHASE09_PROMOTION_MANIFEST,
    SES_MODE_SANDBOX,
    SIGNED_FULL_CHUNKS,
    SIGNED_FULL_HYBRID_VERSIONS,
    STAGING_CADDY_FILE,
    STAGING_COMPOSE_FILE,
    STAGING_ORIGIN_SERVICES,
    STAGING_PRIVATE_NO_HOST_PORT_SERVICES,
    STAGING_REQUIRED_SERVICES,
    SUPABASE_FEATURES,
    TOPOLOGY_SCHEMA_VERSION,
    VALKEY_DIGEST,
    VALKEY_IMAGE,
    VERCEL_ENV_SCHEMA_VERSION,
    VERCEL_FORBIDDEN_KEY_FRAGMENTS,
    VERCEL_PUBLIC_ENV_FILE,
    VERCEL_PUBLIC_ENV_KEYS,
)

_SERVICE_HEADER = "  "
_COMMENT_LINE = re.compile(r"^\s*#.*$", flags=re.MULTILINE)
_HCL_LINE_COMMENT = re.compile(r"//.*?$", flags=re.MULTILINE)
_HCL_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", flags=re.DOTALL)
_ASSIGN_INT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(-?\d+)\b")
_ASSIGN_STR = re.compile(r'\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"([^"]*)"')
_INGRESS_22 = re.compile(
    r"from_port\s*=\s*22\b[\s\S]{0,120}?to_port\s*=\s*22\b",
    flags=re.MULTILINE,
)
_SECRET_FIELD = re.compile(r'"(password|secret|private_key)"\s*:', flags=re.I)


class Phase10TopologyError(RuntimeError):
    """Raised when reviewed staging IaC or inventory violates Packet 1 policy."""


@dataclass(frozen=True, slots=True)
class PolicyFinding:
    """One policy assertion result.

    Attributes:
        check: Stable assertion id.
        passed: True when the committed artifact satisfies the rule.
        detail: Human-readable evidence without secrets.
    """

    check: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PolicyReport:
    """Aggregate Packet 1 IaC/inventory policy result.

    Attributes:
        passed: True when every finding passed.
        findings: Ordered assertion results.
        iac_sha256: Hex digest of concatenated reviewed files.
    """

    passed: bool
    findings: tuple[PolicyFinding, ...]
    iac_sha256: str


def strip_hcl_comments(text: str) -> str:
    """Remove Terraform line and block comments.

    Args:
        text: Raw HCL.

    Returns:
        Comment-stripped HCL. Policy tokens must not live only in comments.
    """

    stripped = _HCL_BLOCK_COMMENT.sub("", text)
    stripped = _HCL_LINE_COMMENT.sub("", stripped)
    return _COMMENT_LINE.sub("", stripped)


def load_terraform_bundle(infra_dir: Path) -> str:
    """Concatenate ``*.tf`` files from the EC2 Terraform directory.

    Args:
        infra_dir: ``infra/ec2`` directory.

    Returns:
        Combined HCL.

    Raises:
        Phase10TopologyError: If no Terraform files exist.
    """

    files = sorted(infra_dir.glob("*.tf"))
    if not files:
        raise Phase10TopologyError("no Terraform files under infra/ec2")
    parts = [path.read_text(encoding="utf-8") for path in files]
    return "\n".join(parts)


def _int_assignments(hcl: str) -> dict[str, list[int]]:
    """Collect integer assignments grouped by attribute name.

    Args:
        hcl: Comment-stripped Terraform.

    Returns:
        Attribute name to integer values.
    """

    grouped: dict[str, list[int]] = {}
    for match in _ASSIGN_INT.finditer(hcl):
        grouped.setdefault(match.group(1), []).append(int(match.group(2)))
    return grouped


def _str_assignments(hcl: str) -> dict[str, list[str]]:
    """Collect string assignments grouped by attribute name.

    Args:
        hcl: Comment-stripped Terraform.

    Returns:
        Attribute name to string values.
    """

    grouped: dict[str, list[str]] = {}
    for match in _ASSIGN_STR.finditer(hcl):
        grouped.setdefault(match.group(1), []).append(match.group(2))
    return grouped


def _require_all_int(values: Sequence[int], expected: int, name: str) -> None:
    """Require every assignment of ``name`` to equal ``expected``.

    Args:
        values: Observed integers.
        expected: Required value.
        name: Attribute name for errors.

    Raises:
        Phase10TopologyError: If missing or not equal to ``expected``.
    """

    if not values:
        raise Phase10TopologyError(f"missing {name}")
    if any(value != expected for value in values):
        raise Phase10TopologyError(f"{name} must be {expected}, found {list(values)}")


def _service_has_ports_key(block: str) -> bool:
    """Return whether a Compose service declares a host ``ports:`` key.

    Args:
        block: Compose service body.

    Returns:
        True when a mapping-level ``ports:`` key is present. Healthcheck URLs
        and ``expose:`` are ignored.
    """

    for line in block.splitlines():
        if re.match(r"^    ports:\s*$", line) or line.startswith("    ports:"):
            return True
    return False


def _require_list(value: object, *, source: str) -> list[object]:
    """Narrow JSON to a list or fail closed.

    Args:
        value: Decoded JSON value.
        source: Error label.

    Returns:
        JSON array.

    Raises:
        Phase10TopologyError: If ``value`` is not a list.
    """

    try:
        return as_json_list(value, source=source)
    except ValueError as exc:
        raise Phase10TopologyError(f"{source} must be a list") from exc


def _require_object(value: object, *, source: str) -> dict[str, object]:
    """Narrow JSON to an object or fail closed.

    Args:
        value: Decoded JSON value.
        source: Error label.

    Returns:
        JSON object.

    Raises:
        Phase10TopologyError: If ``value`` is not an object.
    """

    try:
        return as_json_object(value, source=source)
    except ValueError as exc:
        raise Phase10TopologyError(f"{source} must be an object") from exc


def _require_string_tuple(value: object, *, source: str) -> tuple[str, ...]:
    """Narrow a JSON array to a tuple of strings.

    Args:
        value: Decoded JSON value.
        source: Error label.

    Returns:
        String tuple.

    Raises:
        Phase10TopologyError: If ``value`` is not a list.
    """

    return tuple(str(item) for item in _require_list(value, source=source))


def _require_string_map(value: object, *, source: str) -> dict[str, str]:
    """Narrow a JSON object to string keys and string values.

    Args:
        value: Decoded JSON value.
        source: Error label.

    Returns:
        String map.

    Raises:
        Phase10TopologyError: If ``value`` is not an object.
    """

    obj = _require_object(value, source=source)
    return {str(key): str(val) for key, val in obj.items()}


def assert_no_ssh(hcl: str) -> None:
    """Reject SSH key pairs and port-22 ingress.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10TopologyError: If SSH ingress or ``aws_key_pair`` is present.
    """

    if "aws_key_pair" in hcl:
        raise Phase10TopologyError("aws_key_pair is forbidden; SSM only")
    if re.search(r"\bkey_name\s*=", hcl):
        raise Phase10TopologyError("key_name is forbidden; SSM only")
    if _INGRESS_22.search(hcl):
        raise Phase10TopologyError("SSH ingress on port 22 is forbidden")


def assert_imdsv2(hcl: str) -> None:
    """Require IMDSv2 with hop limit 1 so containers cannot reach IMDS.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10TopologyError: If tokens are missing/optional or hop limit is
            not 1.
    """

    tokens = _str_assignments(hcl).get("http_tokens", [])
    if not tokens:
        raise Phase10TopologyError("IMDSv1: http_tokens is missing")
    if any(value != IMDS_HTTP_TOKENS_REQUIRED for value in tokens):
        raise Phase10TopologyError(
            f"IMDSv1: http_tokens must be {IMDS_HTTP_TOKENS_REQUIRED!r}"
        )
    hops = _int_assignments(hcl).get("http_put_response_hop_limit", [])
    _require_all_int(hops, IMDS_HOP_LIMIT, "http_put_response_hop_limit")
    endpoints = _str_assignments(hcl).get("http_endpoint", [])
    if endpoints and any(value != "enabled" for value in endpoints):
        raise Phase10TopologyError("http_endpoint must stay enabled for SSM")


def assert_encrypted_ebs(hcl: str) -> None:
    """Require encrypted EBS and reject explicit ``encrypted = false``.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10TopologyError: If volumes are unencrypted.
    """

    if re.search(r"encrypted\s*=\s*false", hcl):
        raise Phase10TopologyError("unencrypted EBS is forbidden")
    if "root_block_device" not in hcl:
        raise Phase10TopologyError("root_block_device is missing")
    if not re.search(r"encrypted\s*=\s*true", hcl):
        raise Phase10TopologyError("encrypted EBS is required")


def assert_cloudfront_timeouts(hcl: str) -> None:
    """Require origin read and keep-alive timeouts of 90 seconds.

    Terraform AWS provider 5.100 website still mentions a 60s default upper
    bound. The AWS CloudFront API allows OriginReadTimeout 1-120 (default 30)
    and OriginKeepaliveTimeout 1-300 (default 5). Packet 1 encodes 90 and
    must not silently lower to 60.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10TopologyError: If either timeout is missing or not 90.
    """

    ints = _int_assignments(hcl)
    _require_all_int(
        ints.get("origin_read_timeout", ()),
        ORIGIN_READ_TIMEOUT_SECONDS,
        "origin_read_timeout",
    )
    _require_all_int(
        ints.get("origin_keepalive_timeout", ()),
        ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
        "origin_keepalive_timeout",
    )


def assert_cloudfront_policies(hcl: str) -> None:
    """Require CachingDisabled, origin-request policy, and prefix list.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10TopologyError: If a required CloudFront/WAF token is missing.
    """

    if CACHING_DISABLED_POLICY_ID not in hcl:
        raise Phase10TopologyError("CachingDisabled cache policy id is missing")
    if ALL_VIEWER_EXCEPT_HOST_POLICY_ID not in hcl:
        raise Phase10TopologyError(
            "AllViewerExceptHostHeader origin request policy id is missing"
        )
    if CLOUDFRONT_PREFIX_LIST_NAME not in hcl:
        raise Phase10TopologyError("CloudFront origin-facing prefix list is missing")
    if "aws_wafv2_web_acl" not in hcl:
        raise Phase10TopologyError("WAFv2 web ACL is missing")
    if not re.search(r'scope\s*=\s*"CLOUDFRONT"', hcl):
        raise Phase10TopologyError("WAF scope must be CLOUDFRONT")


def assert_iam_and_provider(hcl: str) -> None:
    """Require SSM-only instance role, ECR pull, and pinned AWS provider.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10TopologyError: If IAM or provider pins are missing.
    """

    if "AmazonSSMManagedInstanceCore" not in hcl:
        raise Phase10TopologyError("AmazonSSMManagedInstanceCore is required")
    has_ecr_token = "ecr:GetAuthorizationToken" in hcl
    has_ecr_managed = "AmazonEC2ContainerRegistryReadOnly" in hcl
    if not has_ecr_token and not has_ecr_managed:
        raise Phase10TopologyError("ECR pull permission is required")
    if "secretsmanager:GetSecretValue" not in hcl:
        raise Phase10TopologyError("Secrets Manager GetSecretValue is required")
    if "smart-rag/staging/" not in hcl:
        raise Phase10TopologyError("Secrets Manager staging name prefix is required")
    if AWS_PROVIDER_CONSTRAINT not in hcl and ">= 5.100" not in hcl:
        raise Phase10TopologyError("hashicorp/aws must be pinned ~> 5.100")
    if "hashicorp/aws" not in hcl:
        raise Phase10TopologyError("hashicorp/aws provider is required")


def assert_sensitive_variables(tf_text: str) -> None:
    """Reject default values on sensitive origin-header variables.

    Args:
        tf_text: Raw ``variables.tf`` (comments kept so ``sensitive`` survives).

    Raises:
        Phase10TopologyError: If a sensitive variable has a non-null default.
    """

    blocks = re.split(r'\nvariable\s+"', tf_text)
    for raw in blocks[1:]:
        name, _, rest = raw.partition('"')
        if not re.search(r"sensitive\s*=\s*true", rest):
            continue
        default_match = re.search(r"default\s*=\s*([^\n]+)", rest)
        if default_match is None:
            continue
        value = default_match.group(1).strip()
        if value not in {"null", "null}"}:
            raise Phase10TopologyError(
                f"sensitive variable {name} must not have a secret default"
            )


def _forbidden_key_assigned(text: str, fragment: str) -> bool:
    """Return whether a forbidden key fragment is assigned.

    Args:
        text: Uppercased env/JSON/HCL.
        fragment: Forbidden fragment such as ``SERVICE_ROLE``.

    Returns:
        True when the fragment appears as a key assignment.
    """

    if fragment not in text:
        return False
    if f"NEXT_PUBLIC_{fragment}" in text:
        return True
    pattern = rf"(NEXT_PUBLIC_[A-Z0-9_]*{fragment}|{fragment})\w*\s*[=:]"
    return re.search(pattern, text) is not None


def assert_no_vercel_secrets(text: str) -> None:
    """Reject Vercel/frontend secret key names in committed env inventories.

    Args:
        text: JSON, HCL, or env text.

    Raises:
        Phase10TopologyError: If a forbidden fragment is assigned as a key.
    """

    upper = text.upper()
    for fragment in VERCEL_FORBIDDEN_KEY_FRAGMENTS:
        if _forbidden_key_assigned(upper, fragment):
            raise Phase10TopologyError(
                f"Vercel/environment secret key fragment {fragment} is forbidden"
            )


def assert_vercel_public_env(payload: Mapping[str, object]) -> None:
    """Require the Vercel inventory to list only public keys.

    Args:
        payload: ``vercel-public-env.json`` object.

    Raises:
        Phase10TopologyError: If schema, keys, or live secrets drift.
    """

    if payload.get("schema_version") != VERCEL_ENV_SCHEMA_VERSION:
        raise Phase10TopologyError("vercel public env schema_version drifted")
    keys = _require_string_tuple(payload.get("allowed_keys"), source="allowed_keys")
    if keys != VERCEL_PUBLIC_ENV_KEYS:
        raise Phase10TopologyError("vercel allowed_keys drifted from contract")
    live = payload.get("live_values")
    if isinstance(live, Mapping) and live:
        raise Phase10TopologyError("vercel live_values must not be committed")
    dumped = json.dumps(dict(payload), sort_keys=True)
    assert_no_vercel_secrets(dumped)
    for key in keys:
        upper_key = key.upper()
        if any(fragment in upper_key for fragment in VERCEL_FORBIDDEN_KEY_FRAGMENTS):
            raise Phase10TopologyError(f"vercel allowed key {key} is a secret")


def compose_service_block(compose_text: str, service: str) -> str:
    """Return the body of one Compose service.

    Args:
        compose_text: Compose YAML.
        service: Service name.

    Returns:
        Indented service body.

    Raises:
        Phase10TopologyError: If the service is missing.
    """

    return _compose_service_block(compose_text, service)


def _compose_service_block(compose_text: str, service: str) -> str:
    """Return the body of one Compose service.

    Args:
        compose_text: Compose YAML.
        service: Service name.

    Returns:
        Indented service body.

    Raises:
        Phase10TopologyError: If the service is missing.
    """

    header = f"{_SERVICE_HEADER}{service}:"
    lines = compose_text.splitlines()
    start: int | None = None
    for index, line in enumerate(lines):
        if line.startswith(header) and (
            len(line) == len(header) or line[len(header) :].startswith(" ")
        ):
            start = index + 1
            break
    if start is None:
        raise Phase10TopologyError(f"compose service missing: {service}")
    collected: list[str] = []
    for line in lines[start:]:
        if line.startswith(_SERVICE_HEADER) and not line.startswith("    "):
            if line.strip().endswith(":") and not line.startswith("    "):
                break
        collected.append(line)
    return "\n".join(collected)


def _compose_declares_host_ports(block: str) -> bool:
    """Return whether a service block publishes host ports.

    Args:
        block: Compose service body.

    Returns:
        True when a ``ports:`` key is present at the service mapping level.
    """

    return _service_has_ports_key(block)


def _compose_has_lightrag_service(compose_text: str) -> bool:
    """Return whether Compose declares a LightRAG server service.

    Args:
        compose_text: Compose YAML.

    Returns:
        True when a top-level ``lightrag`` service exists.
    """

    for line in compose_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("lightrag:") or stripped.startswith("lightrag-"):
            if line.startswith(_SERVICE_HEADER) and not line.startswith("    "):
                return True
    return False


def assert_compose_policy(compose_text: str) -> None:
    """Reject host ports, overlay identity, mutable digests, and LightRAG.

    Args:
        compose_text: Staging Compose source.

    Raises:
        Phase10TopologyError: If private-boundary policy fails.
    """

    if "extends:" in compose_text and "packet8" in compose_text:
        raise Phase10TopologyError("packet8 overlay is forbidden on staging compose")
    if re.search(r"-f\s+docker-compose\.packet8\.yml", compose_text):
        raise Phase10TopologyError("packet8 overlay is forbidden on staging compose")
    if _compose_has_lightrag_service(compose_text):
        raise Phase10TopologyError("LightRAG must stay in-process; no compose service")
    for port in PACKET8_HOST_PORTS | LIGHTRAG_PUBLIC_PORTS:
        if re.search(rf"\b{port}\b", compose_text):
            raise Phase10TopologyError(f"forbidden host/public port {port}")
    for name in STAGING_REQUIRED_SERVICES:
        _compose_service_block(compose_text, name)
    for name in STAGING_PRIVATE_NO_HOST_PORT_SERVICES:
        block = _compose_service_block(compose_text, name)
        if _compose_declares_host_ports(block):
            raise Phase10TopologyError(f"private service {name} publishes host ports")
        if "mem_limit:" not in block:
            raise Phase10TopologyError(f"private service {name} missing mem_limit")
    for name in STAGING_ORIGIN_SERVICES:
        _compose_service_block(compose_text, name)
    paradedb = _compose_service_block(compose_text, "paradedb")
    digest_hex = PARADEDB_DIGEST.split(":", 1)[1]
    if "@sha256:" not in paradedb or digest_hex not in paradedb:
        raise Phase10TopologyError("ParadeDB image must be digest-pinned to Phase 9")
    limits = _compose_service_block(compose_text, "valkey-limits")
    cache = _compose_service_block(compose_text, "valkey-cache")
    valkey_hex = VALKEY_DIGEST.split(":", 1)[1]
    if valkey_hex not in limits or "@sha256:" not in limits:
        raise Phase10TopologyError("valkey-limits image must be digest-pinned")
    if valkey_hex not in cache or "@sha256:" not in cache:
        raise Phase10TopologyError("valkey-cache image must be digest-pinned")
    if "noeviction" not in limits:
        raise Phase10TopologyError("valkey-limits must use noeviction")
    if "allkeys-lru" not in cache:
        raise Phase10TopologyError("valkey-cache must use allkeys-lru")
    if "VALKEY_LIMITS_PASSWORD" not in limits:
        raise Phase10TopologyError("valkey-limits credentials are missing")
    if "VALKEY_CACHE_PASSWORD" not in cache:
        raise Phase10TopologyError("valkey-cache credentials are missing")
    api_id = PHASE09_IMAGE_IDS["api"].removeprefix("sha256:")
    worker_id = PHASE09_IMAGE_IDS["worker"].removeprefix("sha256:")
    crawl_id = PHASE09_IMAGE_IDS["crawl-proxy"].removeprefix("sha256:")
    parser_id = PHASE09_IMAGE_IDS["parser-sandbox"].removeprefix("sha256:")
    if api_id not in compose_text:
        raise Phase10TopologyError("api image id drifted from Phase 9 freeze")
    if worker_id not in compose_text:
        raise Phase10TopologyError("worker image id drifted from Phase 9 freeze")
    if crawl_id not in compose_text:
        raise Phase10TopologyError("crawl-proxy image id drifted from Phase 9 freeze")
    if parser_id not in compose_text:
        raise Phase10TopologyError(
            "parser-sandbox image id drifted from Phase 9 freeze"
        )
    parser = _compose_service_block(compose_text, "parser-sandbox")
    if "network_mode:" not in parser or "none" not in parser:
        raise Phase10TopologyError("parser-sandbox must use network_mode none")


def assert_caddy_policy(caddy_text: str) -> None:
    """Require 90s timeouts, SSE flush, and dual origin-header acceptance.

    Args:
        caddy_text: Staging Caddyfile.

    Raises:
        Phase10TopologyError: If streaming or rotation support is missing.
    """

    normalized = re.sub(r"\s+", " ", caddy_text)
    if "flush_interval -1" not in normalized:
        raise Phase10TopologyError("Caddy must disable SSE buffering")
    timeouts = re.findall(r"(?:read_timeout|write_timeout)\s+(\d+)s", caddy_text)
    if not timeouts:
        raise Phase10TopologyError("Caddy 90s timeouts are missing")
    if any(int(value) != ORIGIN_READ_TIMEOUT_SECONDS for value in timeouts):
        raise Phase10TopologyError("Caddy timeouts must be 90s")
    if "ORIGIN_HEADER_VALUE_CURRENT" not in caddy_text:
        raise Phase10TopologyError("Caddy current origin header value is missing")
    if "ORIGIN_HEADER_VALUE_PREVIOUS" not in caddy_text:
        raise Phase10TopologyError(
            "Caddy previous origin header value is required for dual rotation"
        )
    if "ACTIVE_API_UPSTREAM" not in caddy_text:
        raise Phase10TopologyError("Caddy must proxy the active API slot")
    if "403" not in caddy_text:
        raise Phase10TopologyError("Caddy must deny unmatched origin headers")


def assert_user_data_policy(user_data: str) -> None:
    """Require SSM-friendly bootstrap, metadata deny, and no embedded secrets.

    Args:
        user_data: ``user-data.sh`` source.

    Raises:
        Phase10TopologyError: If bootstrap or metadata deny is missing, or a
            secret-looking assignment is embedded.
    """

    if "169.254.169.254" not in user_data:
        raise Phase10TopologyError("user-data must deny link-local metadata")
    if "DOCKER-USER" not in user_data:
        raise Phase10TopologyError("user-data must use DOCKER-USER")
    lowered = user_data.lower()
    if "docker compose" not in lowered and "docker-compose" not in user_data:
        raise Phase10TopologyError("user-data must start Compose")
    if "ssm" not in lowered:
        raise Phase10TopologyError("user-data must stay SSM-friendly")
    if re.search(r"(AKIA[0-9A-Z]{16}|sk-live-|service_role)", user_data):
        raise Phase10TopologyError("user-data must not embed credentials")


def _envelope_from_inventory(envelope: Mapping[str, object]) -> None:
    """Assert the reduced Phase 9 envelope and reject 10k/1M claims.

    Args:
        envelope: Inventory envelope object.

    Raises:
        Phase10TopologyError: On envelope drift or full-capacity claims.
    """

    if envelope.get("QT-CAP-001-P9") != ENVELOPE_HYBRID_VERSIONS:
        raise Phase10TopologyError("QT-CAP-001-P9 must be 8")
    if envelope.get("QT-CAP-002-P9") != ENVELOPE_CHUNKS:
        raise Phase10TopologyError("QT-CAP-002-P9 must be 16")
    if envelope.get("QT-CAP-005-P8") != ENVELOPE_GRAPH_VERSIONS:
        raise Phase10TopologyError("QT-CAP-005-P8 must be 15")
    if envelope.get("claimed_full_hybrid") is True:
        raise Phase10TopologyError("must not claim QT-CAP-001 10k")
    if envelope.get("claimed_full_chunks") is True:
        raise Phase10TopologyError("must not claim QT-CAP-002 1M")
    hybrid = envelope.get("QT-CAP-001-P9")
    chunks = envelope.get("QT-CAP-002-P9")
    if hybrid == SIGNED_FULL_HYBRID_VERSIONS or chunks == SIGNED_FULL_CHUNKS:
        raise Phase10TopologyError("inventory envelope must not advertise 10k/1M")


def assert_inventory(payload: Mapping[str, object]) -> None:
    """Assert intended topology matches the Packet 1 freeze.

    Args:
        payload: ``intended-topology.json``.

    Raises:
        Phase10TopologyError: On plan/region/artifact/data drift or secrets.
    """

    if payload.get("schema_version") != TOPOLOGY_SCHEMA_VERSION:
        raise Phase10TopologyError("intended topology schema_version drifted")
    if payload.get("aws_region") != INTENDED_AWS_REGION:
        raise Phase10TopologyError("intended AWS region must be us-east-1")
    if payload.get("supabase_region") != INTENDED_SUPABASE_REGION:
        raise Phase10TopologyError("intended Supabase region must be us-east-1")
    if payload.get("supabase_plan") != INTENDED_SUPABASE_PLAN:
        raise Phase10TopologyError("intended Supabase plan must be Pro")
    if payload.get("pg_search_on_managed_supabase") is not False:
        raise Phase10TopologyError(
            "pg_search must not be installed on managed Supabase"
        )
    if payload.get("ses_mode") != SES_MODE_SANDBOX:
        raise Phase10TopologyError("SES must remain sandbox in staging")
    if payload.get("lightrag_deployment") != LIGHTRAG_DEPLOYMENT:
        raise Phase10TopologyError("LightRAG must remain in-process")
    if payload.get("production_data") is not False:
        raise Phase10TopologyError("production data flag must be false")
    if payload.get("holdout_opened") is not False:
        raise Phase10TopologyError("holdout_opened must be false")
    if payload.get("cloudfront_origin_read_timeout_seconds") != (
        ORIGIN_READ_TIMEOUT_SECONDS
    ):
        raise Phase10TopologyError("inventory OriginReadTimeout must be 90")
    if payload.get("cloudfront_origin_keepalive_timeout_seconds") != (
        ORIGIN_KEEPALIVE_TIMEOUT_SECONDS
    ):
        raise Phase10TopologyError("inventory OriginKeepaliveTimeout must be 90")
    if payload.get("cloudfront_cache_policy_id") != CACHING_DISABLED_POLICY_ID:
        raise Phase10TopologyError("inventory CachingDisabled id drifted")
    if payload.get("cloudfront_prefix_list_name") != CLOUDFRONT_PREFIX_LIST_NAME:
        raise Phase10TopologyError("inventory prefix list name drifted")
    if payload.get("imds_http_tokens") != IMDS_HTTP_TOKENS_REQUIRED:
        raise Phase10TopologyError("inventory IMDSv2 tokens drifted")
    if payload.get("imds_hop_limit") != IMDS_HOP_LIMIT:
        raise Phase10TopologyError("inventory hop limit must be 1")
    if payload.get("ssh_ingress") is not False:
        raise Phase10TopologyError("inventory ssh_ingress must be false")
    if payload.get("paradedb_image") != PARADEDB_IMAGE:
        raise Phase10TopologyError("inventory ParadeDB image drifted")
    if payload.get("valkey_image") != VALKEY_IMAGE:
        raise Phase10TopologyError("inventory Valkey image drifted")
    features = _require_string_tuple(
        payload.get("supabase_features"), source="supabase_features"
    )
    if features != SUPABASE_FEATURES:
        raise Phase10TopologyError("supabase_features drifted")
    typed_images = _require_string_map(
        payload.get("phase9_image_ids"), source="phase9_image_ids"
    )
    if typed_images != PHASE09_IMAGE_IDS:
        raise Phase10TopologyError("phase9_image_ids drifted from the freeze")
    _envelope_from_inventory(
        _require_object(payload.get("envelope"), source="envelope")
    )
    vercel_keys = _require_string_tuple(
        payload.get("vercel_public_env_keys"), source="vercel_public_env_keys"
    )
    if vercel_keys != VERCEL_PUBLIC_ENV_KEYS:
        raise Phase10TopologyError("inventory Vercel keys drifted")
    ports = _require_object(
        payload.get("private_service_host_ports"),
        source="private_service_host_ports",
    )
    for name, value in ports.items():
        if value not in ((), [], None, 0):
            raise Phase10TopologyError(
                f"inventory lists host ports for private service {name}"
            )
    dumped = json.dumps(dict(payload), sort_keys=True)
    if _SECRET_FIELD.search(dumped):
        raise Phase10TopologyError("inventory must not contain secret fields")


def assert_phase9_promotion_images(payload: Mapping[str, object]) -> None:
    """Require the Phase 9 promotion manifest image ids to match the freeze.

    Args:
        payload: ``candidate-packet7-promotion-manifest.json``.

    Raises:
        Phase10TopologyError: On digest drift.
    """

    typed = _require_string_map(
        payload.get("candidate_image_ids"), source="candidate_image_ids"
    )
    if typed != PHASE09_IMAGE_IDS:
        raise Phase10TopologyError("Phase 9 promotion image ids drifted")


def assert_synthetic_corpus(payload: Mapping[str, object]) -> None:
    """Reject holdout-open or production-labeled corpus rows.

    Args:
        payload: Phase 9 corpus manifest.

    Raises:
        Phase10TopologyError: If holdout opened, production flags appear, or
            rows are missing.
    """

    if payload.get("holdout_opened") is not False:
        raise Phase10TopologyError("corpus holdout_opened must be false")
    rows = _require_list(payload.get("rows"), source="corpus rows")
    if not rows:
        raise Phase10TopologyError("synthetic corpus rows are missing")
    for item in rows:
        row = _require_object(item, source="corpus row")
        split = str(row.get("split") or "")
        if split not in {"development", "qualification"}:
            raise Phase10TopologyError(f"unapproved corpus split {split}")
        case_id = str(row.get("case_id") or "").lower()
        if "holdout" in case_id or "production" in case_id:
            raise Phase10TopologyError("corpus row is not synthetic/redacted")


def hash_reviewed_files(paths: Sequence[Path]) -> str:
    """Return a SHA-256 over reviewed IaC/inventory bytes.

    Args:
        paths: Files to hash in order.

    Returns:
        Lowercase hex digest.
    """

    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises ``Phase10TopologyError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except Phase10TopologyError as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def assert_committed_policy(repo_root: Path) -> PolicyReport:
    """Assert every committed Packet 1 topology artifact.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10TopologyError: If required files are missing or any check fails.
    """

    infra = repo_root / INFRA_EC2_DIR
    tf_bundle = load_terraform_bundle(infra)
    hcl = strip_hcl_comments(tf_bundle)
    variables = (infra / "variables.tf").read_text(encoding="utf-8")
    compose = (repo_root / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    caddy = (repo_root / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    user_data = (infra / "user-data.sh").read_text(encoding="utf-8")
    inventory = load_json_object(repo_root / INTENDED_TOPOLOGY_FILE)
    vercel = load_json_object(repo_root / VERCEL_PUBLIC_ENV_FILE)
    promotion = load_json_object(repo_root / PHASE09_PROMOTION_MANIFEST)
    corpus = load_json_object(repo_root / PHASE09_CORPUS_MANIFEST)

    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("no_ssh", lambda: assert_no_ssh(hcl)),
        ("imdsv2", lambda: assert_imdsv2(hcl)),
        ("encrypted_ebs", lambda: assert_encrypted_ebs(hcl)),
        ("cloudfront_timeouts", lambda: assert_cloudfront_timeouts(hcl)),
        ("cloudfront_policies", lambda: assert_cloudfront_policies(hcl)),
        ("iam_provider", lambda: assert_iam_and_provider(hcl)),
        ("sensitive_variables", lambda: assert_sensitive_variables(variables)),
        ("compose", lambda: assert_compose_policy(compose)),
        ("caddy", lambda: assert_caddy_policy(caddy)),
        ("user_data", lambda: assert_user_data_policy(user_data)),
        ("inventory", lambda: assert_inventory(inventory)),
        ("vercel_env", lambda: assert_vercel_public_env(vercel)),
        ("phase9_images", lambda: assert_phase9_promotion_images(promotion)),
        ("synthetic_corpus", lambda: assert_synthetic_corpus(corpus)),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed = (
        *sorted(infra.glob("*.tf")),
        repo_root / STAGING_COMPOSE_FILE,
        repo_root / STAGING_CADDY_FILE,
        infra / "user-data.sh",
        repo_root / INTENDED_TOPOLOGY_FILE,
        repo_root / VERCEL_PUBLIC_ENV_FILE,
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
        raise Phase10TopologyError(
            "IaC policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report
