"""Frontend action inventory uniqueness and source mapping."""

from __future__ import annotations

from scripts.check_frontend_action_inventory import check_inventory


def test_frontend_action_inventory_is_unique_and_mapped() -> None:
    """Keep actions have tests and source IDs; removed IDs stay absent."""

    assert check_inventory() == []
