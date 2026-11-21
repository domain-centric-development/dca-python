import typing

from dca_building_blocks import DomainGateway, Factory, OpenHostService, Specification

__dca__ = OpenHostService()  # DCA-STR-005: a module declares an open host service inside the domain


class Ratings(DomainGateway, typing.Protocol):  # DCA-PY-003: no class names the domain gateway
    def rating_of(self, key: str) -> bool: ...


class Scores(DomainGateway, typing.Protocol):
    def score_of(self, key: str) -> int: ...


class LocalScores(Scores):
    def score_of(self, key: str) -> int:
        return len(key)


SCORES: Scores = LocalScores()


def scores() -> Scores:
    return SCORES


class RatedSpecification(Specification[str]):
    def __init__(self, ratings: Ratings) -> None:
        self._ratings = ratings  # DCA-TAC-027: keeps the gateway it received in an attribute

    def is_satisfied_by(self, candidate: str) -> bool:
        return self._ratings.rating_of(candidate)


class ScoreFactory(Factory):
    source = SCORES  # DCA-TAC-027: a class attribute holds a gateway

    def scores(self) -> Scores:  # DCA-TAC-027: a method returns a gateway
        return SCORES  # DCA-TAC-027: reads a module attribute that is a gateway

    def looked_up(self, key: str) -> int:
        return scores().score_of(key)  # DCA-TAC-027: a locator call hands out the gateway

    def built(self, key: str) -> int:
        return LocalScores().score_of(key)  # DCA-TAC-027: builds a gateway implementation
