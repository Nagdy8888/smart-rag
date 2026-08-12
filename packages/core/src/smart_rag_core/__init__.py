"""Shared Smart RAG core package.

This package owns domain models, repositories, provider gateways, retrieval
interfaces, and shared settings used by agents, backend, and worker. It must
not import any ``apps.*`` deployable.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
