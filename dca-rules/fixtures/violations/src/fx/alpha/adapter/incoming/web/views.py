"""GET handlers that drive a command where the eye does not look: a helper, a parameter, a class-based view, a path
that is no literal."""

import django.views

from fx.alpha.adapter.incoming.web.things import router
from fx.alpha.application.add_part import AddPartCommand, TakeInputPort

PREFIX = "/stock"


def _take(port: TakeInputPort) -> None:
    port.execute(None)  # DCA-HEX-014: through a helper the handler calls


@router.get(PREFIX + "/take")
def take(port: TakeInputPort) -> None:
    _take(port)


@router.get(PREFIX)
def given(command: AddPartCommand) -> None:  # DCA-HEX-014: takes the command it drives
    pass


class TakeView(django.views.View):
    def __init__(self, port: TakeInputPort) -> None:
        self._port = port

    def get(self) -> None:
        self._port.execute(None)  # DCA-HEX-014: a class-based view's GET
