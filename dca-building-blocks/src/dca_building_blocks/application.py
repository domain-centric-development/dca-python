"""Application building blocks: the transaction boundary, the port failures and the refusals a use case may answer
with instead of raising."""

from __future__ import annotations

import typing


class Refusal:
    """Marks a case of a closed use-case result that refuses the request.

    A use case answers an expected refusal in one of two styles, chosen per bounded context: it raises a named
    `UseCaseException`, or it returns the refusal as one case of a closed result, a union its caller matches over.
    In the second style every refusing case carries this marker and a case that reports success never does:

        @dataclass(frozen=True)
        class Reserved:
            seat: SeatNumber

        @dataclass(frozen=True)
        class SeatTaken(Refusal):
            seat: SeatNumber

        type ReserveSeatResult = Reserved | SeatTaken

    The incoming adapter matches every case and ends with `case _: assert_never(result)`, so the type checker
    refuses a match that forgets a new case. A refusal rolls back like a failure: see
    `TransactionBoundary.in_transaction_closed`.
    """

    __slots__ = ()


class _Refused(Exception):
    """Carries a returned refusal out of the work, so the boundary rolls it back like a failure."""

    def __init__(self, result: object) -> None:
        super().__init__("refused")
        self.result = result


class TransactionBoundary(typing.Protocol):
    """Runs a unit of work in one transaction: everything it saves and publishes is committed together or not at
    all. A use case holds it as a port; an outgoing adapter implements it; the domain never sees it."""

    def in_transaction[T](self, work: typing.Callable[[], T], /) -> T:
        """Run `work` in a transaction: commit when it returns, roll back when it raises and re-raise."""
        ...

    def in_transaction_closed[T](self, work: typing.Callable[[], T], /) -> T:
        """Run `work` whose answer is a closed result: commit on a success, roll back on a failure and on a
        returned `Refusal`, and hand the refusal back unchanged.

        Every implementation of `in_transaction` gets it without code of its own: the refusal leaves the work as
        an exception, so `in_transaction` rolls it back, and comes back out here as the answer."""

        def refusing() -> T:
            result = work()
            if isinstance(result, Refusal):
                raise _Refused(result)
            return result

        try:
            return self.in_transaction(refusing)
        except _Refused as refused:
            return typing.cast(T, refused.result)


class PortException(Exception):
    """A failure a port's contract declares. A class extends one of the two leaves, `UseCaseException` or
    `OutputPortException`, never this one; nobody handles a port failure as such."""


class InputPortException(PortException):
    """A failure an input port declares. Its one leaf is `UseCaseException`."""


class UseCaseException(InputPortException):
    """A failure a use case names that is not the domain's: the addressed aggregate does not exist, a precondition on
    a second aggregate does not hold. Only the use case raises it; the incoming adapter that drives the port
    translates it. It names no transport vocabulary."""


class OutputPortException(PortException):
    """A failure an output port declares in its contract, beside the port in the application: the outgoing adapter
    raises it because the contract asks for it, the use case that calls the port catches it and decides the answer.
    For an expected failure the caller can answer, not for a failure of the system's own infrastructure."""
