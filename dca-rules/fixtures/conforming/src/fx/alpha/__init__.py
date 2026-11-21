from dca_building_blocks import BoundedContext, Consumes, Translation, Upstream

__dca__ = BoundedContext(
    name="alpha",
    upstreams=(
        # Two relationships towards one context, one per channel: each import is judged by its own (DCA-MAP-008/011).
        Upstream(context="beta", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.API,)),
        Upstream(context="beta", translation=Translation.ANTI_CORRUPTION_LAYER, via=(Consumes.EVENTS,)),
    ),
)
