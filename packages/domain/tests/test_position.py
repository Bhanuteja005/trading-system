from datetime import UTC, datetime
from decimal import Decimal as D

from tsys.domain import Position, Side

OPENED = datetime(2026, 8, 29, 10, 0, tzinfo=UTC)


def _pos(side: Side, entry: str, sl: str) -> Position:
    return Position(
        symbol="NIFTY26000CE", exchange="NFO", side=side, quantity=75,
        entry_price=D(entry), stop_loss=D(sl), target=D("200"),
        opened_at=OPENED, client_order_id="tsysabc",
    )


def test_risk_is_distance_to_stop_times_quantity():
    assert _pos(Side.LONG, "100", "90").risk_rupees == D("750")


def test_short_risk_is_positive():
    assert _pos(Side.SHORT, "100", "110").risk_rupees == D("750")


def test_unrealised_flips_with_side():
    assert _pos(Side.LONG, "100", "90").unrealised(D("110")) == D("750")
    assert _pos(Side.SHORT, "100", "110").unrealised(D("110")) == D("-750")
