# DCA-ERR-006
from dca_building_blocks import PortException
from fx.alpha.application.add_part import AddPartInputPort


def staff_only(user: object) -> bool:
    return user.has_role("staff")  # DCA-HEX-020


def run(port: AddPartInputPort) -> None:  # DCA-ERR-006: translates nothing, handles PortException as such
    try:
        port.execute(None)
    except PortException:
        pass
