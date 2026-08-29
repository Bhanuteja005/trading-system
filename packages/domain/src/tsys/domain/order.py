"""Order intent and outcome.

Every request carries a client_order_id. The broker client uses it to make
placement idempotent, so a retry after a timeout cannot double-fill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class OrderAction(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Product(StrEnum):
    MIS = "MIS"
    NRML = "NRML"


@dataclass(frozen=True, slots=True)
class OrderRequest:
    client_order_id: str
    symbol: str
    exchange: str
    action: OrderAction
    quantity: int
    product: Product = Product.MIS
    price_type: str = "MARKET"

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("quantity must be positive")


@dataclass(frozen=True, slots=True)
class OrderResult:
    ok: bool
    client_order_id: str
    broker_order_id: str | None = None
    error: str | None = None
    submitted_at: datetime | None = None
    deduplicated: bool = False
    """True when the client suppressed a duplicate rather than sending it."""
