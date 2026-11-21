from fx.alpha.application.shared import Ledger


class CountingLedger(Ledger):
    def entries(self) -> int:
        return 0
