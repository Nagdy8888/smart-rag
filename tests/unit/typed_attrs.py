"""Attribute helpers that keep private test access typed without B009/B010."""

from __future__ import annotations


def module_attr(module: object, name: str) -> object:
    """Return a named attribute from a module or instance.

    Args:
        module: Module or instance to read.
        name: Attribute name, including private helpers under test.

    Returns:
        The attribute value.

    Raises:
        AttributeError: If ``name`` is missing.
    """

    return getattr(module, name)


def set_attr(obj: object, name: str, value: object) -> None:
    """Set a named attribute on an instance.

    Args:
        obj: Target instance.
        name: Attribute name, including private fields under test.
        value: Replacement value.
    """

    setattr(obj, name, value)
