"""Parse Phase 10 Packet 3 origin, egress, timeout, and telemetry policy.

Policy checks parse committed Terraform, Compose, Caddy, and allowlists in
Python. They do not apply Terraform, send CDN requests, scan hosts, or treat
missing live alarms as Passed. Fail closed on public origin CIDR ingress,
unpublished-port drift, RFC1918 allowlist entries, sub-90-second CloudFront
timeouts, SSE buffering, missing WAF metrics, and WAF/Caddy limit excess.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Sequence
from pathlib import Path

from smart_rag_core.release.phase10_constants import (
    CADDY_MAX_CONNS_PER_HOST,
    CADDY_MAX_HEADER_BYTES,
    CADDY_MAX_HEADER_BYTES_LIMIT,
    CADDY_READ_HEADER_TIMEOUT_SECONDS,
    CADDY_REQUEST_BODY_BYTES,
    CADDY_REQUEST_BODY_BYTES_LIMIT,
    CLOUDFRONT_PREFIX_LIST_NAME,
    DIRECT_ORIGIN_DENIAL_FILTER_PATTERN,
    DIRECT_ORIGIN_DENIAL_METRIC_NAME,
    EGRESS_DENIAL_FILTER_PATTERN,
    EGRESS_DENIAL_LOG_GROUP,
    EGRESS_DENIAL_METRIC_NAME,
    IMDS_HOP_LIMIT,
    INFRA_EC2_DIR,
    LIGHTRAG_PUBLIC_PORTS,
    ORIGIN_KEEPALIVE_TIMEOUT_SECONDS,
    ORIGIN_READ_TIMEOUT_SECONDS,
    PACKET8_HOST_PORTS,
    PROVIDER_EGRESS_ALLOWLIST_FILE,
    PROVIDER_EGRESS_CADDY_FILE,
    STAGING_CADDY_FILE,
    STAGING_COMPOSE_FILE,
    TELEMETRY_NAMESPACE,
    WAF_ACL_METRIC_SUFFIX,
    WAF_RATE_LIMIT_COMMITTED,
    WAF_RATE_LIMIT_MAX,
    WAF_RULE_METRIC_NAMES,
)
from smart_rag_core.release.phase10_topology import (
    Phase10TopologyError,
    PolicyFinding,
    PolicyReport,
    assert_caddy_policy,
    assert_cloudfront_policies,
    assert_cloudfront_timeouts,
    assert_compose_policy,
    assert_imdsv2,
    assert_user_data_policy,
    compose_service_block,
    hash_reviewed_files,
    load_terraform_bundle,
    strip_hcl_comments,
)

_SIZE = re.compile(
    r"^(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>KB|MB|GB|KIB|MIB|GIB|B)?$",
    flags=re.IGNORECASE,
)
_INGRESS_HEADER = re.compile(r"\bingress\s*\{")
_CADDY_COMMENT = re.compile(r"(?m)^\s*#.*$")
_FORBID_ORIGIN_LITERAL = re.compile(
    r"(?m)^\s*header\s+(?!\{\$)(?:Host\s+\d+\.\d+\.\d+\.\d+|\S+)"
)
_FLUSH_NOT_DISABLED = re.compile(r"(?m)^\s*flush_interval[ \t]+(?!-1)\S+")


def strip_caddy_comments(text: str) -> str:
    """Remove full-line Caddy comments so policy tokens cannot live only there.

    Args:
        text: Caddyfile source.

    Returns:
        Comment-stripped Caddyfile.
    """

    return _CADDY_COMMENT.sub("", text)


class Phase10EgressError(RuntimeError):
    """Raised when Packet 3 origin, egress, timeout, or telemetry policy fails."""


def extract_hcl_block(hcl: str, header: str) -> str:
    """Return the first HCL block whose header text matches.

    Args:
        hcl: Comment-stripped Terraform.
        header: Leading resource/data text such as
            ``resource "aws_security_group" "origin"``.

    Returns:
        The ``{...}`` body including braces.

    Raises:
        Phase10EgressError: If the header or a balanced block is missing.
    """

    index = hcl.find(header)
    if index < 0:
        raise Phase10EgressError(f"missing HCL block {header}")
    brace = hcl.find("{", index)
    if brace < 0:
        raise Phase10EgressError(f"HCL block {header} has no opening brace")
    depth = 0
    for offset, char in enumerate(hcl[brace:], start=brace):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return hcl[brace : offset + 1]
    raise Phase10EgressError(f"HCL block {header} is unbalanced")


def _ingress_blocks(sg_body: str) -> tuple[str, ...]:
    """Return ingress sub-blocks inside a security-group body.

    Args:
        sg_body: Security-group HCL including braces.

    Returns:
        Ingress block texts including braces.
    """

    blocks: list[str] = []
    for match in _INGRESS_HEADER.finditer(sg_body):
        start = sg_body.find("{", match.start())
        depth = 0
        for offset, char in enumerate(sg_body[start:], start=start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    blocks.append(sg_body[match.start() : offset + 1])
                    break
    return tuple(blocks)


def parse_caddy_size(raw: str) -> int:
    """Parse a Caddy size token into bytes.

    Args:
        raw: Token such as ``16KB`` or ``16MB``.

    Returns:
        Size in bytes using 1024-based units.

    Raises:
        Phase10EgressError: If the token cannot be parsed.
    """

    match = _SIZE.match(raw.strip())
    if match is None:
        raise Phase10EgressError(f"unparseable Caddy size {raw!r}")
    value = float(match.group("value"))
    unit = (match.group("unit") or "B").upper()
    multipliers = {
        "B": 1,
        "KB": 1024,
        "KIB": 1024,
        "MB": 1024**2,
        "MIB": 1024**2,
        "GB": 1024**3,
        "GIB": 1024**3,
    }
    return int(value * multipliers[unit])


def _network_items(block: str, key: str = "networks") -> tuple[str, ...]:
    """Return Compose list items under a mapping key.

    Args:
        block: Compose service or file fragment.
        key: Mapping key such as ``networks``.

    Returns:
        Ordered item names. Empty when the key is absent.
    """

    items: list[str] = []
    lines = block.splitlines()
    capturing = False
    key_indent: int | None = None
    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith(f"{key}:"):
            capturing = True
            key_indent = indent
            continue
        if capturing:
            if (
                stripped
                and indent <= (key_indent or 0)
                and not stripped.startswith("-")
            ):
                break
            if stripped.startswith("- "):
                items.append(stripped[2:].strip().strip("\"'"))
    return tuple(item for item in items if item)


def _top_level_network_is_internal(compose_text: str, name: str) -> bool:
    """Return whether a top-level Compose network is ``internal: true``.

    Args:
        compose_text: Compose YAML.
        name: Network name.

    Returns:
        True when the network mapping sets ``internal: true``.
    """

    header = f"  {name}:"
    lines = compose_text.splitlines()
    start: int | None = None
    in_networks = False
    for index, line in enumerate(lines):
        if line.startswith("networks:"):
            in_networks = True
            continue
        if (
            in_networks
            and line
            and not line.startswith(" ")
            and not line.startswith("#")
        ):
            break
        if in_networks and line.startswith(header):
            start = index + 1
            break
    if start is None:
        return False
    collected: list[str] = []
    for line in lines[start:]:
        if (
            line.startswith("  ")
            and not line.startswith("    ")
            and line.strip().endswith(":")
        ):
            break
        if line.startswith("volumes:") or line.startswith("services:"):
            break
        collected.append(line)
    body = "\n".join(collected)
    return bool(re.search(r"internal:\s*true\b", body))


def _allowlist_hosts(text: str) -> tuple[str, ...]:
    """Return non-comment allowlist hostnames.

    Args:
        text: ``allowlist.txt`` contents.

    Returns:
        Host entries without comments or blanks.
    """

    hosts: list[str] = []
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            hosts.append(line)
    return tuple(hosts)


def allowlist_host_is_forbidden(host: str) -> bool:
    """Return whether an allowlist entry is private, link-local, or metadata.

    Args:
        host: Hostname or IP from the provider-egress allowlist.

    Returns:
        True when the entry must not be allow-listed.
    """

    candidate = host[2:] if host.startswith("*.") else host
    lowered = candidate.lower().rstrip(".")
    if lowered in {"localhost", "metadata.google.internal"}:
        return True
    if "169.254.169.254" in lowered:
        return True
    try:
        parsed = ipaddress.ip_address(candidate)
    except ValueError:
        return False
    return bool(
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def assert_origin_security_group(hcl: str) -> None:
    """Require origin HTTPS ingress from the CloudFront prefix list only.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10EgressError: If origin :443 is open to ``0.0.0.0/0`` or the
            prefix list is missing.
    """

    if CLOUDFRONT_PREFIX_LIST_NAME not in hcl:
        raise Phase10EgressError("CloudFront origin-facing prefix list name is missing")
    origin = extract_hcl_block(hcl, 'resource "aws_security_group" "origin"')
    ingresses = _ingress_blocks(origin)
    if not ingresses:
        raise Phase10EgressError("origin security group has no ingress")
    https_found = False
    for block in ingresses:
        if re.search(r"from_port\s*=\s*22\b", block) and re.search(
            r"to_port\s*=\s*22\b", block
        ):
            raise Phase10EgressError("origin security group still allows SSH")
        if "0.0.0.0/0" in block:
            raise Phase10EgressError("origin ingress must not use 0.0.0.0/0")
        https = bool(
            re.search(r"from_port\s*=\s*443\b", block)
            and re.search(r"to_port\s*=\s*443\b", block)
        )
        if not https:
            continue
        https_found = True
        if "cidr_blocks" in block:
            raise Phase10EgressError("origin :443 ingress must not use cidr_blocks")
        if "prefix_list_ids" not in block:
            raise Phase10EgressError("origin :443 ingress must use prefix_list_ids")
    if not https_found:
        raise Phase10EgressError("origin security group missing HTTPS ingress")


def assert_cloudfront_origin_header(hcl: str) -> None:
    """Require a CloudFront custom origin header without committed secrets.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10EgressError: If ``custom_header`` or the name/value variables
            are missing, or a secret-looking literal is committed.
    """

    distribution = extract_hcl_block(
        hcl, 'resource "aws_cloudfront_distribution" "api"'
    )
    if "custom_header" not in distribution:
        raise Phase10EgressError("CloudFront custom origin header is missing")
    if "origin_header_name" not in distribution:
        raise Phase10EgressError("CloudFront origin header name variable is missing")
    if "origin_header_value" not in distribution:
        raise Phase10EgressError("CloudFront origin header value variable is missing")
    if re.search(r'custom_header\s*\{[^}]*value\s*=\s*"[^$]', distribution, flags=re.S):
        raise Phase10EgressError("CloudFront origin header value must not be a literal")


def assert_caddy_direct_origin_deny(caddy_text: str) -> None:
    """Require Caddy 403 for unmatched origin headers and env placeholders.

    Args:
        caddy_text: Staging Caddyfile.

    Raises:
        Phase10EgressError: If the default deny is missing or a literal
            origin header/IP appears.
    """

    assert_caddy_policy(caddy_text)
    active = strip_caddy_comments(caddy_text)
    if 'respond "direct origin denied" 403' not in active:
        raise Phase10EgressError("Caddy must respond 403 for unmatched origin headers")
    if "{$ORIGIN_HEADER_VALUE_CURRENT}" not in active:
        raise Phase10EgressError("Caddy origin matcher must use env placeholders")
    if _FORBID_ORIGIN_LITERAL.search(active):
        raise Phase10EgressError("Caddy must not embed origin IP or header secrets")
    if re.search(r"\b(?:10\.|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)", active):
        raise Phase10EgressError("Caddy must not pin private origin IPs")


def assert_origin_policy(hcl: str, caddy_text: str) -> None:
    """Assert direct-origin rejection policy from committed files.

    Args:
        hcl: Comment-stripped Terraform.
        caddy_text: Staging Caddyfile.

    Raises:
        Phase10EgressError: If origin denial policy fails.
    """

    assert_origin_security_group(hcl)
    assert_cloudfront_origin_header(hcl)
    try:
        assert_caddy_direct_origin_deny(caddy_text)
    except Phase10TopologyError as exc:
        raise Phase10EgressError(str(exc)) from exc


def assert_private_ports_policy(compose_text: str) -> None:
    """Require unpublished private services and no LightRAG/Packet 8 ports.

    Args:
        compose_text: Staging Compose YAML.

    Raises:
        Phase10EgressError: If private-port policy fails.
    """

    try:
        assert_compose_policy(compose_text)
    except Phase10TopologyError as exc:
        raise Phase10EgressError(str(exc)) from exc
    for port in LIGHTRAG_PUBLIC_PORTS | PACKET8_HOST_PORTS:
        if re.search(rf"\b{port}\b", compose_text):
            raise Phase10EgressError(f"forbidden host/public port {port}")
    if "docker-compose.packet8.yml" in compose_text:
        raise Phase10EgressError("packet8 overlay is forbidden on staging compose")


def assert_metadata_deny(hcl: str, user_data: str) -> None:
    """Require hop-limit 1 plus user-data DROP of link-local metadata.

    Args:
        hcl: Comment-stripped Terraform.
        user_data: ``user-data.sh`` source.

    Raises:
        Phase10EgressError: If metadata deny is missing.
    """

    try:
        assert_imdsv2(hcl)
        assert_user_data_policy(user_data)
    except Phase10TopologyError as exc:
        raise Phase10EgressError(str(exc)) from exc
    hops = re.findall(r"http_put_response_hop_limit\s*=\s*(\d+)", hcl)
    if any(int(value) != IMDS_HOP_LIMIT for value in hops):
        raise Phase10EgressError("IMDS hop limit must stay 1")
    if "169.254.169.254" not in user_data or "DROP" not in user_data:
        raise Phase10EgressError("user-data must DROP 169.254.169.254")
    if "DOCKER-USER" not in user_data:
        raise Phase10EgressError("user-data must install DOCKER-USER metadata DROP")


def assert_provider_egress_policy(
    compose_text: str,
    *,
    egress_caddy: str,
    allowlist_text: str,
) -> None:
    """Require deny-by-default provider egress and a public-only allowlist.

    Args:
        compose_text: Staging Compose YAML.
        egress_caddy: Provider-egress Caddyfile.
        allowlist_text: Hostname allowlist.

    Raises:
        Phase10EgressError: If parser/ParadeDB/provider boundaries fail.
    """

    if 'respond "provider egress denied" 403' not in egress_caddy:
        raise Phase10EgressError("provider-egress Caddy must default to 403")
    if "handle {" not in egress_caddy:
        raise Phase10EgressError("provider-egress Caddy must have a default handle")
    hosts = _allowlist_hosts(allowlist_text)
    if not hosts:
        raise Phase10EgressError("provider-egress allowlist is empty")
    forbidden = tuple(host for host in hosts if allowlist_host_is_forbidden(host))
    if forbidden:
        raise Phase10EgressError(
            "provider-egress allowlist contains private/link-local hosts: "
            + ", ".join(forbidden)
        )
    parser = compose_service_block(compose_text, "parser-sandbox")
    if "network_mode:" not in parser or "none" not in parser:
        raise Phase10EgressError("parser-sandbox must use network_mode none")
    if _network_items(parser):
        raise Phase10EgressError("parser-sandbox must not join Compose networks")
    paradedb = compose_service_block(compose_text, "paradedb")
    networks = _network_items(paradedb)
    if networks != ("private",):
        raise Phase10EgressError(
            "paradedb must attach only to the private internal network, "
            f"found {list(networks)}"
        )
    if not _top_level_network_is_internal(compose_text, "private"):
        raise Phase10EgressError("Compose private network must be internal: true")
    worker = compose_service_block(compose_text, "worker")
    worker_nets = _network_items(worker)
    if "crawl_egress" in worker_nets or "provider_egress" in worker_nets:
        raise Phase10EgressError("worker must not join public egress networks")


def assert_caddy_waf_controls(caddy_text: str, hcl: str) -> None:
    """Require WAF size/rate/bot rules and Caddy header/body/connection caps.

    Args:
        caddy_text: Staging Caddyfile.
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10EgressError: If a required control is missing or excessive.
    """

    header_match = re.search(r"max_header_size\s+(\S+)", caddy_text)
    if header_match is None:
        raise Phase10EgressError("Caddy max_header_size is missing")
    header_bytes = parse_caddy_size(header_match.group(1))
    if header_bytes > CADDY_MAX_HEADER_BYTES_LIMIT:
        raise Phase10EgressError("Caddy max_header_size exceeds the Packet 3 cap")
    if header_bytes != CADDY_MAX_HEADER_BYTES:
        raise Phase10EgressError(
            f"Caddy max_header_size must be {CADDY_MAX_HEADER_BYTES} bytes"
        )
    body_match = re.search(
        r"request_body\s*\{[^}]*max_size\s+(\S+)", caddy_text, flags=re.S
    )
    if body_match is None:
        raise Phase10EgressError("Caddy request_body max_size is missing")
    body_bytes = parse_caddy_size(body_match.group(1))
    if body_bytes > CADDY_REQUEST_BODY_BYTES_LIMIT:
        raise Phase10EgressError("Caddy request_body max_size exceeds FastAPI envelope")
    if body_bytes != CADDY_REQUEST_BODY_BYTES:
        raise Phase10EgressError(
            f"Caddy request_body max_size must be {CADDY_REQUEST_BODY_BYTES} bytes"
        )
    if f"max_conns_per_host {CADDY_MAX_CONNS_PER_HOST}" not in caddy_text:
        raise Phase10EgressError("Caddy reverse_proxy max_conns_per_host is missing")
    header_timeouts = re.findall(r"read_header_timeout\s+(\d+)s", caddy_text)
    if not header_timeouts:
        raise Phase10EgressError("Caddy read_header_timeout is missing")
    if any(
        int(value) != CADDY_READ_HEADER_TIMEOUT_SECONDS for value in header_timeouts
    ):
        raise Phase10EgressError("Caddy read_header_timeout must be 15s")
    if "AWSManagedRulesCommonRuleSet" not in hcl:
        raise Phase10EgressError("WAF CommonRuleSet size/bot baseline is missing")
    if "AWSManagedRulesKnownBadInputsRuleSet" not in hcl:
        raise Phase10EgressError("WAF KnownBadInputs rule is missing")
    if "AWSManagedRulesAmazonIpReputationList" not in hcl:
        raise Phase10EgressError("WAF IP reputation/bot rule is missing")
    if "rate_based_statement" not in hcl:
        raise Phase10EgressError("WAF rate-based rule is missing")
    limits = [int(value) for value in re.findall(r"limit\s*=\s*(\d+)", hcl)]
    if not limits:
        raise Phase10EgressError("WAF rate limit value is missing")
    if any(value > WAF_RATE_LIMIT_MAX for value in limits):
        raise Phase10EgressError("WAF rate limit exceeds the Packet 3 cap")
    if WAF_RATE_LIMIT_COMMITTED not in limits:
        raise Phase10EgressError("WAF committed rate limit drifted")


def assert_timeout_policy(hcl: str, caddy_text: str) -> None:
    """Require CloudFront/Caddy 90s timeouts, no buffering, CachingDisabled.

    Args:
        hcl: Comment-stripped Terraform.
        caddy_text: Staging Caddyfile.

    Raises:
        Phase10EgressError: If timeouts are missing, 60, or buffering remains.
    """

    try:
        assert_cloudfront_timeouts(hcl)
        assert_cloudfront_policies(hcl)
        assert_caddy_policy(caddy_text)
        assert_caddy_waf_controls(caddy_text, hcl)
    except Phase10TopologyError as exc:
        raise Phase10EgressError(str(exc)) from exc
    reads = [
        int(value) for value in re.findall(r"origin_read_timeout\s*=\s*(\d+)", hcl)
    ]
    if any(value == 60 for value in reads):
        raise Phase10EgressError("origin_read_timeout 60 is forbidden")
    if any(value != ORIGIN_READ_TIMEOUT_SECONDS for value in reads):
        raise Phase10EgressError("origin_read_timeout must stay 90")
    keeps = [
        int(value) for value in re.findall(r"origin_keepalive_timeout\s*=\s*(\d+)", hcl)
    ]
    if any(value != ORIGIN_KEEPALIVE_TIMEOUT_SECONDS for value in keeps):
        raise Phase10EgressError("origin_keepalive_timeout must stay 90")
    active = strip_caddy_comments(caddy_text)
    if "flush_interval -1" not in re.sub(r"\s+", " ", active):
        raise Phase10EgressError("Caddy flush_interval -1 is missing")
    if _FLUSH_NOT_DISABLED.search(active):
        raise Phase10EgressError("Caddy flush_interval must stay -1")


def assert_telemetry_policy(hcl: str) -> None:
    """Require WAF CloudWatch metric names and egress-denial log filters.

    Live alarm delivery is classified separately and must not be treated as
    Passed here.

    Args:
        hcl: Comment-stripped Terraform.

    Raises:
        Phase10EgressError: If metric names or log filters are missing.
    """

    if "visibility_config" not in hcl:
        raise Phase10EgressError("WAF visibility_config is missing")
    if not re.search(r"cloudwatch_metrics_enabled\s*=\s*true", hcl):
        raise Phase10EgressError("WAF CloudWatch metrics must be enabled")
    for name in WAF_RULE_METRIC_NAMES:
        if not re.search(rf'metric_name\s*=\s*"{re.escape(name)}"', hcl):
            raise Phase10EgressError(f"WAF metric_name {name!r} is missing")
    if WAF_ACL_METRIC_SUFFIX not in hcl:
        raise Phase10EgressError("WAF ACL metric_name suffix is missing")
    if 'resource "aws_cloudwatch_log_group" "egress_denials"' not in hcl:
        raise Phase10EgressError("egress-denial CloudWatch log group is missing")
    if EGRESS_DENIAL_LOG_GROUP not in hcl:
        raise Phase10EgressError("egress-denial log group name drifted")
    if EGRESS_DENIAL_METRIC_NAME not in hcl:
        raise Phase10EgressError("ProviderEgressDenials metric is missing")
    if DIRECT_ORIGIN_DENIAL_METRIC_NAME not in hcl:
        raise Phase10EgressError("DirectOriginDenials metric is missing")
    if TELEMETRY_NAMESPACE not in hcl:
        raise Phase10EgressError("SmartRag/Staging metric namespace is missing")
    if EGRESS_DENIAL_FILTER_PATTERN not in hcl:
        raise Phase10EgressError("egress denial filter pattern is missing")
    if DIRECT_ORIGIN_DENIAL_FILTER_PATTERN not in hcl:
        raise Phase10EgressError("direct-origin denial filter pattern is missing")
    if "aws_cloudwatch_metric_alarm" not in hcl:
        raise Phase10EgressError("egress-denial CloudWatch alarm resource is missing")
    if not re.search(r"actions_enabled\s*=\s*false", hcl):
        raise Phase10EgressError(
            "egress-denial alarm must keep actions disabled until live routing exists"
        )


def _run_check(check: str, callback: Callable[[], None]) -> PolicyFinding:
    """Run one assertion and convert failures into findings.

    Args:
        check: Assertion id.
        callback: Zero-argument callable that raises ``Phase10EgressError``.

    Returns:
        Finding with pass/fail detail.
    """

    try:
        callback()
    except Phase10EgressError as exc:
        return PolicyFinding(check=check, passed=False, detail=str(exc))
    return PolicyFinding(check=check, passed=True, detail="ok")


def assert_packet3_policy(repo_root: Path) -> PolicyReport:
    """Assert every committed Packet 3 origin/egress/timeout/telemetry artifact.

    Args:
        repo_root: Repository root.

    Returns:
        Policy report. ``passed`` is False when any finding failed.

    Raises:
        Phase10EgressError: If required files are missing or any check fails.
    """

    infra = repo_root / INFRA_EC2_DIR
    tf_bundle = load_terraform_bundle(infra)
    hcl = strip_hcl_comments(tf_bundle)
    compose = (repo_root / STAGING_COMPOSE_FILE).read_text(encoding="utf-8")
    caddy = (repo_root / STAGING_CADDY_FILE).read_text(encoding="utf-8")
    user_data = (infra / "user-data.sh").read_text(encoding="utf-8")
    egress_caddy = (repo_root / PROVIDER_EGRESS_CADDY_FILE).read_text(encoding="utf-8")
    allowlist = (repo_root / PROVIDER_EGRESS_ALLOWLIST_FILE).read_text(encoding="utf-8")

    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("origin", lambda: assert_origin_policy(hcl, caddy)),
        ("private_ports", lambda: assert_private_ports_policy(compose)),
        ("metadata", lambda: assert_metadata_deny(hcl, user_data)),
        (
            "egress",
            lambda: assert_provider_egress_policy(
                compose, egress_caddy=egress_caddy, allowlist_text=allowlist
            ),
        ),
        ("timeouts", lambda: assert_timeout_policy(hcl, caddy)),
        ("telemetry", lambda: assert_telemetry_policy(hcl)),
    )
    findings = tuple(_run_check(name, callback) for name, callback in checks)
    reviewed: Sequence[Path] = (
        *sorted(infra.glob("*.tf")),
        repo_root / STAGING_COMPOSE_FILE,
        repo_root / STAGING_CADDY_FILE,
        infra / "user-data.sh",
        repo_root / PROVIDER_EGRESS_CADDY_FILE,
        repo_root / PROVIDER_EGRESS_ALLOWLIST_FILE,
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
        raise Phase10EgressError(
            "Packet 3 policy failed: " + ", ".join(failed) + f" ({details})"
        )
    return report
