# DCA-ERR-006
from dca_building_blocks import PortException
from fx.alpha.application.add_part import AddPartInputPort


def staff_only(user: object) -> bool:
    return user.has_role("staff")  # DCA-HEX-020


def run(port: AddPartInputPort) -> None:  # DCA-ERR-006: translates nothing, handles PortException as such
    try:
        port.execute(None)
    except PortException:  # DCA-ERR-010: the port failures' common base
        pass


def run_all(port: AddPartInputPort) -> None:
    try:
        port.execute(None)
    except Exception:  # DCA-ERR-010: every failure alike
        return


def run_again(port: AddPartInputPort) -> None:
    try:
        port.execute(None)
    except:  # noqa: E722 DCA-ERR-010: a re-raise unchanged is reported as well; the clean-up belongs in finally
        raise
