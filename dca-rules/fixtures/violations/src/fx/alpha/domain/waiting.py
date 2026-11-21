import asyncio  # DCA-ONI-004: an asynchronous runtime
from collections.abc import Awaitable  # DCA-ONI-004: an asynchronous type outside a gateway or service


async def settle() -> None:  # DCA-ONI-004
    await asyncio.sleep(0)  # DCA-ONI-004
