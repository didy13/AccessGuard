"""
Provider registry.

Providers register themselves by name so the router can look them up
dynamically.  Adding a new provider only requires:
  1. Creating a new module that subclasses BaseProvider
  2. Calling register_provider("my_provider", MyProvider) in server/providers/__init__.py
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import BaseProvider

_registry: dict[str, type[BaseProvider]] = {}


def register_provider(name: str, cls: type[BaseProvider]) -> None:
    _registry[name.lower()] = cls


def get_provider(name: str) -> BaseProvider:
    cls = _registry.get(name.lower())
    if cls is None:
        raise ValueError(
            f"Provider '{name}' is not registered. "
            f"Available: {list(_registry.keys())}"
        )
    return cls()


def list_providers() -> list[str]:
    return list(_registry.keys())


# Module-level alias for convenience
registry = _registry
