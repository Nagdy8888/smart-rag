"""Attribute helpers that keep private test access typed without B009/B010."""

from __future__ import annotations

from typing import Any


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


def typed_attr(obj: object, name: str) -> Any:
    """Return a named attribute typed as ``Any`` for private test seams.

    Args:
        obj: Module or instance to read.
        name: Attribute name, including protected fields under test.

    Returns:
        The attribute value.

    Raises:
        AttributeError: If ``name`` is missing.
    """

    return getattr(obj, name)


def set_attr(obj: object, name: str, value: object) -> None:
    """Set a named attribute on an instance.

    Args:
        obj: Target instance.
        name: Attribute name, including private fields under test.
        value: Replacement value.
    """

    setattr(obj, name, value)


def ignore_args(*_args: object, **_kwargs: object) -> None:
    """Typed no-op used as a monkeypatch or callback stand-in.

    Args:
        *_args: Ignored positional arguments.
        **_kwargs: Ignored keyword arguments.
    """

    return None
