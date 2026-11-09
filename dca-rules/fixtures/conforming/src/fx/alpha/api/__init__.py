"""An open host service of functions: the package declares itself, as a context does."""

from dca_building_blocks import OpenHostService

__dca__ = OpenHostService()


def known(key: str) -> bool:
    return bool(key.strip())
