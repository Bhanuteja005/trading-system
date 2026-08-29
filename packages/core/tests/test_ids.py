from datetime import date
from decimal import Decimal as D

from tsys.core import client_order_id

BASE = dict(
    index="NIFTY", side="LONG", entry=D("100"), stop_loss=D("90"),
    target=D("130"), session=date(2026, 8, 29),
)


def test_identical_intent_is_identical_id():
    """This is what makes a retry safe: the same decision cannot double-fill."""
    assert client_order_id(**BASE) == client_order_id(**BASE)


def test_scale_of_decimal_does_not_change_the_id():
    assert client_order_id(**BASE) == client_order_id(**{**BASE, "entry": D("100.0000")})


def test_any_level_change_changes_the_id():
    for field, value in [("entry", D("101")), ("stop_loss", D("91")), ("target", D("131"))]:
        assert client_order_id(**{**BASE, field: value}) != client_order_id(**BASE)


def test_side_and_session_are_part_of_identity():
    assert client_order_id(**{**BASE, "side": "SHORT"}) != client_order_id(**BASE)
    assert client_order_id(**{**BASE, "session": date(2026, 8, 30)}) != client_order_id(**BASE)


def test_sequence_allows_a_deliberate_re_entry():
    assert client_order_id(**BASE, sequence=1) != client_order_id(**BASE)
