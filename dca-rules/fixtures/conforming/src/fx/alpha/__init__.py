from dca_building_blocks import BoundedContext, Consumes, Translation, Upstream

__dca__ = BoundedContext(
    name="alpha",
    upstreams=(
        Upstream(context="beta", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.API, Consumes.EVENTS)),
    ),
)
