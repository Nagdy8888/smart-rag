"""Bake-off image package init for parser adapters.

The host adapter registry loads every format parser. This image must stay
Markdown-only, so the registry is omitted. The runner imports
``markdown_adapter`` directly.
"""
