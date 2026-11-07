# DCA-USE-018: drives the commands of two features
from __future__ import annotations

from django.db import transaction

from fx.alpha.adapter.outgoing.store import InMemory  # DCA-HEX-006
from fx.alpha.application.add_part import (
    AddPartCommand,
    Refused,
    Taken,
    TakeInputPort,
)
from fx.alpha.application.add_part import AddPartUseCase  # DCA-HEX-011
from fx.alpha.application.shared import ThingRepository  # DCA-HEX-003
from fx.alpha.application.things.remove_part import RemovePartCommand
from fx.alpha.domain.model import Part, Pricing, Status, Thing, ThingFull  # DCA-HEX-012: Pricing
from fx.alpha.infrastructure import config  # DCA-HEX-004
from fx.beta.adapter.incoming import things as beta_things  # DCA-CYC-004
from fx.beta.domain.model import BetaModel  # DCA-HEX-007, DCA-STR-006
from fx.delta.api import DeltaApi  # DCA-MAP-008: behind an ACL the api channel belongs to the outgoing adapter


class Router:
    def get(self, path: str): ...

    def post(self, path: str): ...


router = Router()


@router.get("/things")  # DCA-HEX-014, DCA-USE-018
def list_things(port: TakeInputPort) -> str:
    AddPartCommand()  # DCA-HEX-014
    RemovePartCommand("x")  # DCA-HEX-014
    Part(None, None)  # DCA-TAC-005
    Thing(None, None, None, 0)  # DCA-TAC-023
    ThingFull()  # DCA-ERR-009
    result = port.execute(AddPartCommand())  # DCA-HEX-014
    match result:
        case Taken():
            return Status.OPEN.name  # DCA-HEX-016
        case Refused():
            return "refused"
        case _:  # DCA-PY-006
            return "other"


@router.post("/things")
@transaction.atomic  # DCA-LAY-004
def add_thing() -> None:
    pass
