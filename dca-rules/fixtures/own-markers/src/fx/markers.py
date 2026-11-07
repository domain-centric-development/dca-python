"""A copy of the building blocks the project keeps for itself."""


class Value:
    pass


class Id(Value):
    pass


class AggregateRoot:
    pass


class BoundedContext:
    def __init__(self, name: str) -> None:
        self.name = name
