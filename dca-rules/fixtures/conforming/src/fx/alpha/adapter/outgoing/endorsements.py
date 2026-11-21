from fx.alpha.domain.endorsement import Endorsements, Ratings
from fx.alpha.domain.thing import ThingId


class EveryThingEndorsed(Endorsements):
    def endorsed(self, thing_id: ThingId, /) -> bool:
        return bool(thing_id.value)


class EveryThingRated(Ratings):
    async def endorsed_later(self, thing_id: ThingId, /) -> bool:
        return bool(thing_id.value)
