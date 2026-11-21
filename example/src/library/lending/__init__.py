"""Lending: copies on the shelf or on loan, the members who borrow them, their reservations. It answers its refusals as
cases of closed results and learns of new copies from the catalogue's `CopyAcquired`."""

from dca_building_blocks import BoundedContext, Consumes, ExternalUpstream, Interaction, Status, Translation, Upstream

__dca__ = BoundedContext(
    name="lending",
    description="copies on the shelf or on loan, the members who borrow them, their reservations",
    upstreams=(
        Upstream(
            context="catalogue",
            translation=Translation.ANTI_CORRUPTION_LAYER,
            via=(Consumes.EVENTS,),
            rationale="a copy the catalogue acquired is shelved for lending; lending keeps its own model of a copy",
        ),
    ),
    external_upstreams=(
        ExternalUpstream(
            name="membership-office",
            translation=Translation.ANTI_CORRUPTION_LAYER,
            interaction=Interaction.OUTBOUND,
            protocol="in process",
            exchanges="whether a member is suspended",
            rationale="the office keeps the members' standing; lending asks it through the MemberStandings gateway",
            status=Status.IMPLEMENTED,
        ),
    ),
)
