#!/usr/bin/env python3
"""Bounded LangSmith agent evaluation over synthetic development cases.

Dry-run validates selection and ceilings with no LangSmith, database, agent,
or provider work. Live execution admits the production query graph in-process.
Holdout stays sealed. This tool does not claim Combined +10pp.
"""

from __future__ import annotations

import sys
from pathlib import Path

# ruff: noqa: E402 — repo root must precede local package imports for CLI use.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from agent_eval_cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
