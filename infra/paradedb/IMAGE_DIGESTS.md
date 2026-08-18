# Image digest provenance (Phase 9 Packet 7 Trivy repair, 2026-08-18)

paradedb/paradedb:pg17@sha256:dca046b8a0ddd070c368d5254cbb7f596b3b7bc67bc2efa7c0fbe881087883bb
valkey/valkey:8.1-alpine@sha256:a038175878d66b9d274fbf8be73c0305e93798b83917647f167e18cef3c71eec
library/python:3.11-slim-trixie@sha256:9c900dea9e8fb7e16277c179b555cc72d29a352dbc33cff48ad5a0412fd5bfc7
library/python:3.11-alpine@sha256:6857d2dae63e052057f2db389a7061188ac9a92a3fa8d402bde68f36df6fada1
library/node:20-alpine@sha256:fb4cd12c85ee03686f6af5362a0b0d56d50c58a04632e6c0fb8363f609372293
gcr.io/distroless/cc-debian13:nonroot@sha256:d97bc0a941b8d4be647dc0ee75b264ddbb772f1ac5ba690a4309c00723b23775

# uv binary copy source used in Dockerfiles (tag pin; digest re-verified at build):
# ghcr.io/astral-sh/uv:0.11.23
#
# CPython API/worker/agents: trixie builder (glibc wheels, including frozen
# pyarrow 19.0.1) plus an ldd closure of libffi/native-wheel libs copied onto
# distroless/cc-debian13 so perl-base is not in the scanned runtime.
# Crawl-proxy uses the same distroless runtime; stdlib ssl comes from
# distroless/cc. Parser and frontend stay Alpine.
# See docs/adr/ADR-alpine-application-bases-trivy.md.
