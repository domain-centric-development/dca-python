from dca_building_blocks import (
    BoundedContext,
    Consumes,
    ExternalUpstream,
    Interaction,
    Partnership,
    Translation,
    Upstream,
)

__dca__ = BoundedContext(
    name="alpha",
    upstreams=(
        Upstream(context="alpha", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.API,)),  # DCA-MAP-004
        Upstream(context="nowhere", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.API,)),  # DCA-MAP-004
        Upstream(context="beta", translation=Translation.CONFORMIST, via=(Consumes.API,)),
        Upstream(context="delta", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.API, Consumes.API)),  # DCA-MAP-005
        Upstream(context="epsilon", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.EVENTS,)),  # DCA-MAP-007
    ),
    external_upstreams=(
        ExternalUpstream(name="", translation=Translation.ANTI_CORRUPTION_LAYER, interaction=Interaction.OUTBOUND),  # DCA-MAP-002
        ExternalUpstream(name="payments", translation=Translation.ANTI_CORRUPTION_LAYER,
                         interaction=Interaction.OUTBOUND, contract_packages=("payments_sdk",)),
    ),
    partnerships=(Partnership(context="beta"),),  # DCA-MAP-012: beta does not declare it back
)
