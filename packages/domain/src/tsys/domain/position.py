"""An open position and the exposure it represents."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from .decision import Side


@dataclass(frozen=True, slots=True)
class Position:
    symbol: str
    exchange: str
    side: Side
    quantity: int
    entry_price: Decimal
    stop_loss: Decimal
    target: Decimal
    opened_at: datetime
    client_order_id: str

    @property
    def risk_rupees(self) -> Decimal:
        per_unit = (
            self.entry_price - self.stop_loss
            if self.side is Side.LONG
            else self.stop_loss - self.entry_price
        )
        return abs(per_unit) * self.quantity

    def unrealised(self, last: Decimal) -> Decimal:
        direction = 1 if self.side is Side.LONG else -1
        return (last - self.entry_price) * self.quantity * direction
