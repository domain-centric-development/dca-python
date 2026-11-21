"""What the catalogue and lending share: the identities of a title and a copy, the clock and the source of fresh
identities, and the in-memory store with its outbox, inbox and relay."""

from dca_building_blocks import SharedKernel

__dca__ = SharedKernel(description="the identities of titles and copies, the clock, the store, outbox and inbox")
