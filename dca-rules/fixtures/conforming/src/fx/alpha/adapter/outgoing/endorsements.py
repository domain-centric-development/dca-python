from fx.alpha.domain.endorsement import Endorsements
from fx.alpha.domain.thing import ThingId


class EveryThingEndorsed(Endorsements):
    def endorsed(self, thing_id: ThingId, /) -> bool:
        return bool(thing_id.value)
