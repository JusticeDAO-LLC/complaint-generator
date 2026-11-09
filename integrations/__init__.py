"""Optional integrations, initialized when explicitly requested."""

from importlib import import_module as _import_module


__all__ = ["ipfs_datasets"]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = _import_module(f".{name}", __name__)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
