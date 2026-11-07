from __future__ import annotations

import dataclasses
from typing import assert_never

from dca_building_blocks import Timestamp
from fx.alpha.adapter.incoming.web.routing import router
from fx.alpha.application.add_part import AddPartCommand, AddPartInputPort, PartAccepted, ThingMissing
from fx.alpha.application.count_things import CountThingsInputPort, CountThingsQuery, TooFewThings
from fx.alpha.domain.thing import Label, PartId, ThingFull, ThingId
from fx.sharedkernel.domain.owner import OwnerId


@dataclasses.dataclass(frozen=True)
class ThingViewModel:
    count: int


@dataclasses.dataclass(frozen=True)
class PartResponse:
    status: int
    part: str


@router.post("/things/{thing_id}/parts")
def add_part(port: AddPartInputPort, thing_id: str, owner: str, part: str, label: str, now: Timestamp) -> PartResponse:
    command = AddPartCommand(ThingId(thing_id), OwnerId(owner), PartId(part), Label(label), now)
    try:
        result = port.execute(command)
    except ThingFull:
        return PartResponse(409, part)
    match result:
        case PartAccepted():
            return PartResponse(201, part)
        case ThingMissing():
            return PartResponse(404, part)
        case _:
            assert_never(result)


@router.get("/things/count")
def count(port: CountThingsInputPort) -> ThingViewModel:
    try:
        return ThingViewModel(port.execute(CountThingsQuery(1)).count)
    except TooFewThings as refused:
        return ThingViewModel(refused.count)
