"""Parsing and the freshness contract, exercised against recorded fixtures."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from tsys.config import TradingViewSettings
from tsys.core import DataUnavailable, StaleData
from tsys.domain import MarketSnapshot
from tsys.tv import TradingViewClient, build_snapshot, parse_bars, parse_quote

FIX = Path(__file__).parent / "fixtures"
QUOTE = (FIX / "quote_nifty.json").read_bytes()
BARS = (FIX / "ohlcv_nifty.json").read_bytes()


def test_parse_quote_from_fixture():
    q = parse_quote(QUOTE, symbol="NIFTY")
    assert q.last == Decimal("24812.35")
    assert q.spread == Decimal("0.9")


def test_parse_bars_sorted_and_typed():
    bars = parse_bars(BARS)
    assert len(bars) == 220
    assert all(isinstance(b.close, Decimal) for b in bars)
    assert list(bars) == sorted(bars, key=lambda b: b.ts)


def test_cli_error_envelope_raises():
    with pytest.raises(DataUnavailable, match="CLI error"):
        parse_quote(b'{"error":"CDP not connected"}', symbol="NIFTY")


def test_non_json_raises_rather_than_returning_none():
    with pytest.raises(DataUnavailable, match="non-JSON"):
        parse_quote(b"<html>502 Bad Gateway</html>", symbol="NIFTY")


def test_empty_bar_array_raises():
    with pytest.raises(DataUnavailable, match="empty"):
        parse_bars(b'{"ok":true,"data":[]}')


def test_unparseable_price_raises():
    with pytest.raises(DataUnavailable, match="unparseable"):
        parse_quote(b'{"ok":true,"data":{"last":"n/a"}}', symbol="NIFTY")


# ---- the freshness / availability contract ---------------------------------

class FakeRunner:
    def __init__(self, mapping, fail=None):
        self.mapping, self.fail, self.calls = mapping, fail or {}, []

    def __call__(self, args):
        self.calls.append(args)
        key = args[0]
        if key in self.fail:
            raise self.fail[key]
        return self.mapping.get(key, b'{"ok":true,"data":{}}')


def _client(**overrides):
    s = TradingViewSettings(**overrides)
    return TradingViewClient(s, runner=FakeRunner({"quote": QUOTE, "ohlcv": BARS}))


def test_snapshot_happy_path():
    snap = _client().snapshot("NIFTY", timeframe="5")
    assert isinstance(snap, MarketSnapshot)
    assert snap.index == "NIFTY" and len(snap.bars) == 220


def test_insufficient_history_raises():
    c = TradingViewClient(
        TradingViewSettings(TV_MIN_BARS=500),
        runner=FakeRunner({"quote": QUOTE, "ohlcv": BARS}),
    )
    with pytest.raises(DataUnavailable, match="need 500"):
        c.snapshot("NIFTY")


def test_stale_snapshot_raises_rather_than_being_traded():
    snap = build_snapshot(
        index="NIFTY", timeframe="5", quote_raw=QUOTE, bars_raw=BARS,
        captured_at=datetime.now(UTC) - timedelta(seconds=600),
    )
    assert snap.is_stale(90.0)


def test_cdp_down_is_reported_not_guessed():
    c = TradingViewClient(
        TradingViewSettings(),
        runner=FakeRunner({}, fail={"status": DataUnavailable("CDP refused")}),
    )
    assert c.health() is False
