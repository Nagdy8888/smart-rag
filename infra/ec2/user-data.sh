#!/bin/bash
# Rebuildable EC2 user-data for Phase 10 Packet 1. SSM Session Manager is the
# only operator path. Do not embed AWS keys, database URLs, or origin secrets.
set -euo pipefail

log() {
  echo "[smart-rag-staging] $*"
}

log "SSM-friendly bootstrap starting"

dnf install -y docker iptables
systemctl enable --now docker
systemctl enable --now amazon-ssm-agent || true

install -d -m 0755 /opt/smart-rag
install -d -m 0755 /opt/smart-rag/provider-egress

# Metadata deny: host and containers must not reach IMDS. Hop limit 1 is also
# set in Terraform; this is defense in depth.
iptables -C OUTPUT -d 169.254.169.254/32 -j DROP 2>/dev/null || \
  iptables -I OUTPUT -d 169.254.169.254/32 -j DROP
if iptables -nL DOCKER-USER >/dev/null 2>&1; then
  iptables -C DOCKER-USER -d 169.254.169.254/32 -j DROP 2>/dev/null || \
    iptables -I DOCKER-USER -d 169.254.169.254/32 -j DROP
else
  iptables -N DOCKER-USER || true
  iptables -I DOCKER-USER -d 169.254.169.254/32 -j DROP
fi

# Named-path default-deny stub for container egress. Packet 3 proves monitored
# denials. Host OUTPUT stays able to reach 443 for SSM/ECR.
if [[ -f /opt/smart-rag/provider-egress/allowlist.txt ]]; then
  iptables -N SMART_RAG_EGRESS 2>/dev/null || true
  iptables -F SMART_RAG_EGRESS
  iptables -A SMART_RAG_EGRESS -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
  iptables -A SMART_RAG_EGRESS -d 169.254.169.254/32 -j DROP
  while IFS= read -r host || [[ -n "${host}" ]]; do
    [[ -z "${host}" || "${host}" =~ ^# ]] && continue
    iptables -A SMART_RAG_EGRESS -p tcp --dport 443 -m comment --comment "${host}" -j RETURN
  done < /opt/smart-rag/provider-egress/allowlist.txt
  iptables -A SMART_RAG_EGRESS -j DROP
  iptables -C DOCKER-USER -j SMART_RAG_EGRESS 2>/dev/null || \
    iptables -A DOCKER-USER -j SMART_RAG_EGRESS
fi

if [[ -f /opt/smart-rag/docker-compose.staging.yml ]]; then
  log "starting docker compose from /opt/smart-rag"
  cd /opt/smart-rag
  docker compose -f docker-compose.staging.yml up -d
else
  log "compose file not yet copied by SSM; instance is rebuildable once files exist"
fi

log "bootstrap finished"
