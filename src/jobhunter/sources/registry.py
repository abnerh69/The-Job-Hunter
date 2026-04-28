from typing import Type

from jobhunter.sources.base import BaseSource

_REGISTRY: dict[str, Type[BaseSource]] = {}


def register_source(cls: Type[BaseSource]) -> Type[BaseSource]:
    """
    Decorator to register a source class in the registry.

    Args:
        cls: The BaseSource subclass to register.

    Returns:
        The registered class.
    """
    _REGISTRY[cls.__name__] = cls
    return cls


def get_all_sources() -> list[Type[BaseSource]]:
    """
    Retrieves all registered source classes.

    Returns:
        A list of registered BaseSource subclasses.
    """
    return list(_REGISTRY.values())
