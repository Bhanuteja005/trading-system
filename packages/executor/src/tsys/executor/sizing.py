"""Position sizing. Risk decides quantity; quantity is never chosen first.

Lots are floored, never rounded up: rounding up would breach the per-trade cap
that the whole risk mandate rests on.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from tsys.domain import Levels, Side


@dataclass(frozen=True, slots=True)
class Sizing:
    lots: int
    quantity: int
    risk_rupees: Decimal
    risk_per_unit: Decimal


def size_position(
    *,
    levels: Levels,
    side: Side,
    lot_size: int,
    max_risk_rupees: Decimal,
    min_risk_rupees: Decimal,
    max_lots: int = 20,
) -> Sizing | str:
    """Return a Sizing, or a string explaining why no size is acceptable."""
    if lot_size <= 0:
        return f"invalid lot size {lot_size}"

    risk_per_unit = levels.risk_per_unit(side)
    if risk_per_unit <= 0:
        return "non-positive risk per unit"

    risk_per_lot = risk_per_unit * lot_size
    if risk_per_lot > max_risk_rupees:
        return (
            f"one lot risks {risk_per_lot:.2f}, above the {max_risk_rupees:.2f} cap; "
            "the stop is too wide for this lot size"
        )

    lots = int((max_risk_rupees / risk_per_lot).to_integral_value(rounding=ROUND_DOWN))
    lots = min(lots, max_lots)
    if lots < 1:
        return "sizing floors to zero lots"

    risk = risk_per_lot * lots
    if risk < min_risk_rupees:
        return f"risk {risk:.2f} below the {min_risk_rupees:.2f} floor; not worth the slippage"

    return Sizing(
        lots=lots,
        quantity=lots * lot_size,
        risk_rupees=risk.quantize(Decimal("0.01")),
        risk_per_unit=risk_per_unit,
    )
