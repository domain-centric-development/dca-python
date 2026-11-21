from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class Settings:
    """The kernel's technical support, shared by every context's outgoing adapters."""

    limit: int = 1000
