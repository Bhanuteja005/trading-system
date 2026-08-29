from datetime import datetime
from decimal import Decimal as D

from tsys.config import RiskSettings
from tsys.core import IST
from tsys.domain import Levels, Position, Side

from tsys.executor.risk import PortfolioState, check
from tsys.executor.sizing import size_position

MAX, MIN = D("3000"), D("750")


def _size(entry="100", sl="90", lot=75, **kw):
    return size_position(
        levels=Levels(D(entry), D(sl), D("130")), side=Side.LONG, lot_size=lot,
        max_risk_rupees=kw.get("max_risk", MAX), min_risk_rupees=kw.get("min_risk", MIN),
    )


def test_lots_are_floored_never_rounded_up():
    """10 risk/unit x 75 = 750/lot; 3000/750 = 4 exactly."""
    s = _size()
    assert s.lots == 4 and s.quantity == 300 and s.risk_rupees == D("3000.00")


def test_sizing_never_exceeds_the_cap():
    s = _size(entry="100", sl="93")  # 7/unit x 75 = 525/lot -> 5 lots = 2625
    assert s.lots == 5 and s.risk_rupees <= MAX


def test_stop_too_wide_for_one_lot_is_refused():
    r = _size(entry="200", sl="100")  # 100/unit x 75 = 7500 > 3000
    assert isinstance(r, str) and "too wide" in r


def test_risk_below_the_floor_is_refused():
    r = _size(entry="100", sl="99.9", lot=1)  # 0.1/lot -> way under the floor
    assert isinstance(r, str) and "below" in r


# ---- portfolio limits -------------------------------------------------------

OPEN = datetime(2026, 8, 28, 10, 0, tzinfo=IST)   # Friday, market open
LATE = datetime(2026, 8, 28, 15, 5, tzinfo=IST)
WEEKEND = datetime(2026, 8, 29, 10, 0, tzinfo=IST)


def _pos(symbol="SENSEX74000CE", risk="1500"):
    entry = D("100")
    return Position(
        symbol=symbol, exchange="BFO", side=Side.LONG, quantity=75,
        entry_price=entry, stop_loss=entry - D(risk) / 75, target=D("200"),
        opened_at=OPEN, client_order_id="x",
    )


def _settings(tmp_path, **kw):
    return RiskSettings(TSYS_KILL_FILE=tmp_path / "KILL", **kw)


def test_clean_state_is_allowed(tmp_path):
    assert check(settings=_settings(tmp_path), state=PortfolioState(),
                 new_risk=D("1000"), index="NIFTY", now=OPEN) is None


def test_kill_switch_blocks_everything(tmp_path):
    (tmp_path / "KILL").write_text("halt")
    r = check(settings=_settings(tmp_path), state=PortfolioState(),
              new_risk=D("1000"), index="NIFTY", now=OPEN)
    assert r and "kill switch" in r


def test_no_new_entries_late_in_the_session(tmp_path):
    r = check(settings=_settings(tmp_path), state=PortfolioState(),
              new_risk=D("1000"), index="NIFTY", now=LATE)
    assert r and "no new entries" in r


def test_closed_market_is_refused(tmp_path):
    r = check(settings=_settings(tmp_path), state=PortfolioState(),
              new_risk=D("1000"), index="NIFTY", now=WEEKEND)
    assert r and "closed" in r


def test_daily_loss_limit_halts_entries(tmp_path):
    state = PortfolioState(realised_pnl_today=D("-6000"))
    r = check(settings=_settings(tmp_path), state=state,
              new_risk=D("1000"), index="NIFTY", now=OPEN)
    assert r and "daily loss limit" in r


def test_daily_profit_target_halts_entries(tmp_path):
    state = PortfolioState(realised_pnl_today=D("9500"))
    r = check(settings=_settings(tmp_path), state=state,
              new_risk=D("1000"), index="NIFTY", now=OPEN)
    assert r and "profit target" in r


def test_max_open_positions(tmp_path):
    state = PortfolioState(open_positions=(_pos("AAA"), _pos("BBB")))
    r = check(settings=_settings(tmp_path), state=state,
              new_risk=D("100"), index="NIFTY", now=OPEN)
    assert r and "max 2" in r


def test_no_doubling_up_on_the_same_index(tmp_path):
    state = PortfolioState(open_positions=(_pos("NIFTY26000CE"),))
    r = check(settings=_settings(tmp_path), state=state,
              new_risk=D("100"), index="NIFTY", now=OPEN)
    assert r and "already exposed" in r


def test_portfolio_risk_ceiling_stops_stacking(tmp_path):
    """Two trades each inside the per-trade cap can still breach the total."""
    state = PortfolioState(open_positions=(_pos("SENSEX74000CE", risk="5000"),))
    r = check(settings=_settings(tmp_path), state=state,
              new_risk=D("2500"), index="NIFTY", now=OPEN)
    assert r and "ceiling" in r
