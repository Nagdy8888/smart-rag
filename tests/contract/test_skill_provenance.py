"""Imported skill checksums must describe actual repository files."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import cast


def test_imported_skill_manifest_matches_file_bytes() -> None:
    """Bind checksum metadata to source bytes, including secret-scan exceptions."""
    root = Path(__file__).resolve().parents[2] / ".agents" / "skills"
    manifest = json.loads((root / "upstream-manifest.json").read_text(encoding="utf8"))
    skills = cast(dict[str, dict[str, object]], manifest["skills"])
    assert skills, "An empty manifest cannot verify installed skills"
    for name, entry in skills.items():
        skill_root = (root / name).resolve()
        assert skill_root.is_relative_to(root.resolve())
        files = cast(dict[str, str], entry["files"])
        assert "SKILL.md" in files
        for relative, expected in files.items():
            source = (skill_root / relative).resolve()
            assert source.is_relative_to(skill_root)
            assert re.fullmatch(r"[0-9a-f]{64}", expected), source
            assert hashlib.sha256(source.read_bytes()).hexdigest() == expected, source
