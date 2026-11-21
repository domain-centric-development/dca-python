"""The catalogue: the titles the library holds and the copies it acquired of them. It answers its refusals by raising
named exceptions and publishes `CopyAcquired` for the contexts that lend the copies."""

from dca_building_blocks import BoundedContext

__dca__ = BoundedContext(
    name="catalogue",
    description="the titles the library holds and the copies it acquired of them",
)
