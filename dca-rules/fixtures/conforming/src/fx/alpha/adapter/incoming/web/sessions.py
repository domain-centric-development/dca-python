from typing import Protocol


class SessionStore(Protocol):
    """An incoming adapter's own abstraction, no port (DCA-TAC-018)."""

    def remembered(self, key: str) -> str: ...
