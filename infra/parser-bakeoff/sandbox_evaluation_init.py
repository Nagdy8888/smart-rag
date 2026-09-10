"""Bake-off image package init for ``smart_rag_core.evaluation``.

The host package exports calibration loaders at import time. Those imports
pull SharedSettings, which this no-network AnyDoc image must not install.
Submodules such as ``parser_bakeoff.anydoc`` remain importable.
"""
