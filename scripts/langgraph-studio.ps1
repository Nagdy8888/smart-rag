# UTF-8: pinned langgraph-cli help/dev banners include emoji that crash
# Windows cp1252 consoles (UnicodeEncodeError). Paths in langgraph.json are
# relative to apps/agents. See docs/development/LANGGRAPH_STUDIO.md.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $root "apps\agents")
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run langgraph dev --config langgraph.json --no-browser --allow-blocking @args
