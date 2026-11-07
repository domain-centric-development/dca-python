from dca_building_blocks import OpenHostService


class BetaCatalog(OpenHostService):
    def knows(self, key: str) -> bool:
        return bool(key)


def lookup(key: str) -> bool:
    return BetaCatalog().knows(key)
