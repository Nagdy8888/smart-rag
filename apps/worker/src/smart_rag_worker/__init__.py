"""Worker process package for durable Smart RAG jobs.

Phase 1 provides import and console-script startup contracts only. Queue
claim/lease behavior is owned by later phases.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
